from conftest import (
    BROKEN_FIX,
    FINDINGS,
    FIXED_CODE,
    NONE_SORT_CODE,
    NONE_SORT_QUERY,
    ScriptedLLM,
    diagnosis,
    grade_all,
    plan,
)

from troubleshooter.schemas import CodeFindings, Diagnosis, RelevanceGrades, TriagePlan, TroubleshootRequest
from troubleshooter.service import TroubleshootService
from troubleshooter.state import CODE_ANALYST, DOC_RESEARCHER, GITHUB_RESEARCHER, VALIDATOR


def make_service(settings, retriever, diagnoses, **plan_overrides):
    llm = ScriptedLLM(
        {
            TriagePlan: plan(**plan_overrides),
            RelevanceGrades: grade_all,
            CodeFindings: FINDINGS,
            Diagnosis: diagnoses,
        }
    )
    return TroubleshootService(settings, llm=llm, retriever=retriever), llm


def test_verified_fix_end_to_end(settings, retriever):
    service, llm = make_service(settings, retriever, [diagnosis(FIXED_CODE)])
    report = service.run(TroubleshootRequest(query=NONE_SORT_QUERY, code=NONE_SORT_CODE))

    assert report.error_type == "TypeError"
    assert report.reproduced is True
    assert report.fixes[0].validation.status == "verified"
    assert report.fixes[0].validation.grounded
    assert "+    ranked = sorted(scores, reverse=True)" in report.fixes[0].diff
    assert any(source.kind == "documentation" for source in report.sources)
    assert report.revisions == 0
    assert llm.calls == ["triage", "grade_documents", "analyze_code", "diagnose"]
    assert report.llm_calls == 4


def test_failed_fix_triggers_one_revision(settings, retriever):
    service, llm = make_service(settings, retriever, [diagnosis(BROKEN_FIX), diagnosis(FIXED_CODE)])
    report = service.run(TroubleshootRequest(query=NONE_SORT_QUERY, code=NONE_SORT_CODE))

    assert report.revisions == 1
    assert report.fixes[0].validation.status == "verified"
    assert llm.calls.count("diagnose") == 2


def test_revision_budget_is_respected(settings, retriever):
    service, llm = make_service(settings, retriever, [diagnosis(BROKEN_FIX), diagnosis(BROKEN_FIX)])
    report = service.run(TroubleshootRequest(query=NONE_SORT_QUERY, code=NONE_SORT_CODE))

    assert llm.calls.count("diagnose") == settings.max_revisions + 1
    assert report.fixes[0].validation.status == "failed"
    assert any("unverified" in warning for warning in report.warnings)


def test_unknown_citations_are_flagged(settings, retriever):
    service, _ = make_service(settings, retriever, [diagnosis(FIXED_CODE, citations=("D1", "D99"))])
    report = service.run(TroubleshootRequest(query=NONE_SORT_QUERY, code=NONE_SORT_CODE))

    validation = report.fixes[0].validation
    assert not validation.grounded
    assert validation.unknown_citations == ["D99"]


def test_question_without_code_skips_code_analysis(settings, retriever):
    service, llm = make_service(settings, retriever, [diagnosis(None)])
    report = service.run(TroubleshootRequest(query="Why does list.sort() return None?"))

    assert "analyze_code" not in llm.calls
    assert report.fixes[0].validation.status == "not_run"
    assert report.reproduced is None


def test_stream_emits_steps_then_report(settings, retriever):
    service, _ = make_service(settings, retriever, [diagnosis(FIXED_CODE)])
    events = list(service.stream(TroubleshootRequest(query=NONE_SORT_QUERY, code=NONE_SORT_CODE)))

    kinds = [e["event"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "report"
    nodes = [e["data"]["node"] for e in events if e["event"] == "step"]
    assert nodes.index(DOC_RESEARCHER) < nodes.index(CODE_ANALYST) < nodes.index(VALIDATOR)


def test_low_doc_coverage_escalates_to_github(settings, retriever, monkeypatch):
    from troubleshooter.agents import researchers

    monkeypatch.setattr(researchers, "search_issues", lambda query, token=None: [])
    github_settings = settings.model_copy(update={"enable_github_search": True})
    llm = ScriptedLLM(
        {
            TriagePlan: plan(analyze_code=False),
            RelevanceGrades: RelevanceGrades(relevant_ids=[], coverage="insufficient", missing_information="n/a"),
            Diagnosis: [diagnosis(FIXED_CODE)],
        }
    )
    service = TroubleshootService(github_settings, llm=llm, retriever=retriever)
    events = list(service.stream(TroubleshootRequest(query=NONE_SORT_QUERY, code=NONE_SORT_CODE)))

    nodes = [e["data"]["node"] for e in events if e["event"] == "step"]
    assert GITHUB_RESEARCHER in nodes

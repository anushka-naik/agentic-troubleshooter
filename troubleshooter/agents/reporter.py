"""Assemble the final report from state.

No LLM call here: the report is a projection of what the agents found, so
validation labels and warnings cannot be paraphrased away.
"""

import difflib
import time

from troubleshooter.agents.code_analyst import reproduces
from troubleshooter.agents.common import Stopwatch, step
from troubleshooter.config import Settings
from troubleshooter.schemas import Report, ReportFix
from troubleshooter.state import REPORTER, GraphState

STATUS_LABELS = {
    "verified": "Verified in sandbox",
    "failed": "Failed validation",
    "not_verifiable": "Not verifiable",
    "not_run": "Not executed",
}


def unified_diff(original: str | None, patched: str | None) -> str | None:
    if not original or not patched:
        return None
    lines = difflib.unified_diff(
        original.rstrip("\n").splitlines(),
        patched.rstrip("\n").splitlines(),
        fromfile="original.py",
        tofile="patched.py",
        lineterm="",
    )
    return "\n".join(lines) or None


class Reporter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def __call__(self, state: GraphState) -> dict:
        watch = Stopwatch()
        diagnosis = state["diagnosis"]
        plan = state["plan"]
        validations = {v.fix_index: v for v in state.get("validations", [])}

        fixes = [
            ReportFix(
                title=fix.title,
                explanation=fix.explanation,
                patched_code=fix.patched_code,
                test_code=fix.test_code,
                diff=unified_diff(state.get("code"), fix.patched_code),
                citations=fix.citations,
                validation=validations[index],
            )
            for index, fix in enumerate(diagnosis.fixes)
        ]
        reproduced = reproduces(state["parsed"], state.get("reproduction"))
        cited = {c for fix in diagnosis.fixes for c in fix.citations}
        sources = sorted(state.get("evidence", []), key=lambda e: (e.id not in cited, e.id))

        steps = state.get("steps", []) + step(REPORTER, "Compiled final report", watch)
        report = Report(
            problem_summary=plan.problem_summary,
            error_type=plan.error_type,
            category=plan.category,
            root_cause=diagnosis.root_cause,
            confidence=diagnosis.confidence,
            reasoning=diagnosis.reasoning,
            reproduced=reproduced,
            fixes=fixes,
            sources=sources,
            open_questions=diagnosis.open_questions,
            warnings=self._warnings(state, fixes, reproduced),
            steps=steps,
            revisions=max(state.get("diagnosis_round", 1) - 1, 0),
            llm_calls=state.get("llm_calls", 0),
            duration_ms=int((time.time() - state["started_at"]) * 1000),
        )
        report.markdown = render_markdown(report)
        return {"report": report, "steps": steps[-1:]}

    def _warnings(self, state: GraphState, fixes: list[ReportFix], reproduced: bool | None) -> list[str]:
        warnings = []
        for n, fix in enumerate(fixes, start=1):
            v = fix.validation
            if v.status != "verified":
                warnings.append(f"Fix {n} ({fix.title}) is unverified: {v.detail}")
            if v.unknown_citations:
                warnings.append(f"Fix {n} cites evidence that does not exist: {', '.join(v.unknown_citations)}")
            elif not v.grounded:
                warnings.append(f"Fix {n} does not cite any evidence.")
        if reproduced is False:
            warnings.append("The reported error was not reproduced in the standard-library-only sandbox.")
        if state.get("doc_coverage") == "insufficient":
            warnings.append("The documentation index had little relevant material; treat the diagnosis with care.")
        if state.get("code") and not self.settings.enable_code_execution:
            warnings.append("Code execution is disabled, so no fix was executed.")
        return warnings


def render_markdown(report: Report) -> str:
    out = [
        "# Debugging Report",
        "",
        f"**Problem:** {report.problem_summary}",
        f"**Error:** {report.error_type or 'none'} · **Category:** {report.category.replace('_', ' ')}"
        f" · **Confidence:** {report.confidence}",
    ]
    if report.reproduced is not None:
        out.append(f"**Reproduced in sandbox:** {'yes' if report.reproduced else 'no'}")
    out += ["", "## Root cause", "", report.root_cause, "", report.reasoning, "", "## Suggested fixes"]
    for n, fix in enumerate(report.fixes, start=1):
        label = STATUS_LABELS[fix.validation.status]
        out += ["", f"### {n}. {fix.title} — {label}", "", fix.explanation, ""]
        out.append(f"_Validation:_ {fix.validation.detail}")
        if fix.citations:
            out.append(f"_Sources:_ {', '.join(fix.citations)}")
        if fix.diff:
            out += ["", "```diff", fix.diff.rstrip(), "```"]
        if fix.test_code:
            out += ["", "Regression check:", "", "```python", fix.test_code.rstrip(), "```"]
    if report.warnings:
        out += ["", "## Warnings", ""] + [f"- {w}" for w in report.warnings]
    if report.open_questions:
        out += ["", "## Open questions", ""] + [f"- {q}" for q in report.open_questions]
    out += ["", "## Evidence", ""] + [f"- **[{e.id}]** {e.title} — {e.source}" for e in report.sources]
    out += [
        "",
        f"_{len(report.steps)} steps · {report.llm_calls} LLM calls · {report.revisions} revision(s)"
        f" · {report.duration_ms / 1000:.1f}s_",
    ]
    return "\n".join(out)

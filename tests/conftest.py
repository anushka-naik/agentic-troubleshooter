import re
from collections.abc import Callable

import pytest

from troubleshooter.config import Settings, get_settings
from troubleshooter.rag.retriever import HybridRetriever
from troubleshooter.schemas import CodeFindings, Diagnosis, ProposedFix, RelevanceGrades, TriagePlan

NONE_SORT_CODE = """def top_scores(scores):
    ranked = scores.sort(reverse=True)
    return ranked[:3]


print(top_scores([42, 17, 99, 63]))
"""

NONE_SORT_QUERY = """Traceback (most recent call last):
  File "leaderboard.py", line 6, in <module>
    print(top_scores([42, 17, 99, 63]))
  File "leaderboard.py", line 3, in top_scores
    return ranked[:3]
TypeError: 'NoneType' object is not subscriptable"""

FIXED_CODE = NONE_SORT_CODE.replace("scores.sort(reverse=True)", "sorted(scores, reverse=True)")
BROKEN_FIX = NONE_SORT_CODE.replace("scores.sort(reverse=True)", "scores.sorted(reverse=True)")


class ScriptedLLM:
    """Deterministic stand-in for the chat model, keyed by output schema."""

    name = "scripted"

    def __init__(self, responses: dict[type, Callable[[str], object] | list]):
        self.responses = responses
        self.calls: list[str] = []

    def generate(self, schema, system, user, *, run_name):
        self.calls.append(run_name)
        response = self.responses[schema]
        if isinstance(response, list):
            response = response.pop(0)
        return response(user) if callable(response) else response


def plan(**overrides) -> TriagePlan:
    values = dict(
        problem_summary="top_scores crashes when slicing the sorted list.",
        error_type="TypeError",
        category="runtime_exception",
        search_queries=["list.sort returns None", "NoneType object is not subscriptable"],
        libraries=[],
        analyze_code=True,
        search_github=False,
        rationale="Standard library error with code supplied.",
    )
    values.update(overrides)
    return TriagePlan(**values)


def grade_all(user: str) -> RelevanceGrades:
    ids = re.findall(r'<chunk id="([^"]+)"', user)
    return RelevanceGrades(relevant_ids=ids[:3], coverage="sufficient", missing_information=None)


def diagnosis(patched_code: str | None, citations=("D1", "E1")) -> Diagnosis:
    return Diagnosis(
        root_cause="list.sort() sorts in place and returns None, so ranked is None.",
        confidence="high",
        reasoning="E1 reproduces the TypeError; D1 documents that sort returns None.",
        fixes=[
            ProposedFix(
                title="Use sorted()",
                explanation="sorted() returns a new list.",
                patched_code=patched_code,
                test_code=None,
                citations=list(citations),
            )
        ],
        open_questions=[],
    )


FINDINGS = CodeFindings(
    suspect_lines=[2, 3],
    observations=["ranked is assigned the return value of list.sort()"],
    hypothesis="ranked is None because list.sort() returns None.",
)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings().model_copy(update={"enable_github_search": False})


@pytest.fixture(scope="session")
def retriever(settings) -> HybridRetriever:
    return HybridRetriever.from_settings(settings)

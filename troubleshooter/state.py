import operator
from typing import Annotated, TypedDict

from troubleshooter.schemas import (
    CodeFindings,
    Diagnosis,
    Evidence,
    ExecutionResult,
    FixValidation,
    ParsedTraceback,
    Report,
    StepLog,
    TriagePlan,
)

# Node names double as the routing vocabulary of the supervisor.
TRIAGE = "triage"
SUPERVISOR = "supervisor"
DOC_RESEARCHER = "doc_researcher"
CODE_ANALYST = "code_analyst"
GITHUB_RESEARCHER = "github_researcher"
DIAGNOSTICIAN = "diagnostician"
VALIDATOR = "validator"
REPORTER = "reporter"

SPECIALISTS = (DOC_RESEARCHER, CODE_ANALYST, GITHUB_RESEARCHER)


class GraphState(TypedDict, total=False):
    # Input
    query: str
    code: str | None
    enable_github: bool
    started_at: float

    # Triage and routing
    parsed: ParsedTraceback
    plan: TriagePlan
    pending: list[str]
    next_step: str
    completed: Annotated[list[str], operator.add]

    # Investigation
    evidence: Annotated[list[Evidence], operator.add]
    doc_coverage: str
    code_findings: CodeFindings | None
    reproduction: ExecutionResult | None

    # Diagnosis and validation loop
    diagnosis: Diagnosis
    diagnosis_round: int
    validated_round: int
    validations: list[FixValidation]
    feedback: str | None

    # Bookkeeping
    steps: Annotated[list[StepLog], operator.add]
    llm_calls: Annotated[int, operator.add]
    report: Report

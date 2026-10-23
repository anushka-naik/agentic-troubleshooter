"""Data contracts shared by agents, the API and the evaluation harness.

Models in the "LLM outputs" section are passed to the model as strict JSON
schemas, so every field is required (nullable where optional) and has no default.
"""

from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Requests and tool outputs
# --------------------------------------------------------------------------- #


class TroubleshootRequest(BaseModel):
    query: str = Field(min_length=3, max_length=20_000)
    code: str | None = Field(default=None, max_length=50_000)
    enable_github: bool = True


class StackFrame(BaseModel):
    file: str
    line: int
    function: str
    source: str | None = None


class ParsedTraceback(BaseModel):
    exception_type: str | None = None
    exception_module: str | None = None
    message: str | None = None
    frames: list[StackFrame] = []
    warnings: list[str] = []

    @property
    def found(self) -> bool:
        return self.exception_type is not None


class ExecutionResult(BaseModel):
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    exception: ParsedTraceback | None = None

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class Evidence(BaseModel):
    id: str
    kind: Literal["documentation", "github_issue", "code_analysis", "execution"]
    title: str
    source: str
    snippet: str
    score: float | None = None


# --------------------------------------------------------------------------- #
# LLM outputs
# --------------------------------------------------------------------------- #

Category = Literal[
    "runtime_exception",
    "syntax_error",
    "import_or_environment",
    "logic_bug_no_exception",
    "conceptual_question",
    "other",
]


class TriagePlan(BaseModel):
    problem_summary: str = Field(description="One or two sentences restating the developer's problem.")
    error_type: str | None = Field(description="Exception class name, or null if there is no exception.")
    category: Category
    search_queries: list[str] = Field(description="2-4 short documentation search queries targeting the likely cause.")
    libraries: list[str] = Field(description="Third-party libraries involved. Empty for standard library only.")
    analyze_code: bool = Field(description="Whether static analysis and reproduction of the code would help.")
    search_github: bool = Field(
        description="Whether searching GitHub issues is likely to help (third-party library bugs, version issues)."
    )
    rationale: str = Field(description="Why these investigation steps were chosen.")


class RelevanceGrades(BaseModel):
    relevant_ids: list[str] = Field(description="IDs of chunks that directly help explain or fix this problem.")
    coverage: Literal["sufficient", "partial", "insufficient"]
    missing_information: str | None = Field(description="What the documentation does not cover, if anything.")


class CodeFindings(BaseModel):
    suspect_lines: list[int] = Field(description="1-based line numbers in the submitted code most likely at fault.")
    observations: list[str] = Field(description="Concrete facts about the code relevant to the failure.")
    hypothesis: str = Field(description="The most likely mechanism of failure, grounded in the observations.")


class ProposedFix(BaseModel):
    title: str
    explanation: str = Field(description="What to change and why it addresses the root cause.")
    patched_code: str | None = Field(
        description="The full corrected version of the submitted code, runnable as a script. Null if no code was given."
    )
    test_code: str | None = Field(
        description=(
            "Optional assertions appended after patched_code that must pass when fixed and fail on the original. "
            "Use for bugs that do not raise an exception. Null if not needed."
        )
    )
    citations: list[str] = Field(description="Evidence IDs (e.g. D1, G2, C1) supporting this fix.")


class Diagnosis(BaseModel):
    root_cause: str = Field(description="The specific root cause, naming the exact construct at fault.")
    confidence: Literal["high", "medium", "low"]
    reasoning: str = Field(description="How the evidence supports the root cause, citing evidence IDs.")
    fixes: list[ProposedFix] = Field(description="1-3 fixes, best first.")
    open_questions: list[str] = Field(description="Information that would change or confirm the diagnosis.")


# --------------------------------------------------------------------------- #
# Validation and report
# --------------------------------------------------------------------------- #

ValidationStatus = Literal["verified", "failed", "not_verifiable", "not_run"]


class FixValidation(BaseModel):
    fix_index: int
    status: ValidationStatus
    detail: str
    grounded: bool
    unknown_citations: list[str] = []
    patched_run: ExecutionResult | None = None


class StepLog(BaseModel):
    agent: str
    summary: str
    duration_ms: int
    details: dict = {}


class ReportFix(BaseModel):
    title: str
    explanation: str
    patched_code: str | None
    test_code: str | None
    diff: str | None
    citations: list[str]
    validation: FixValidation


class Report(BaseModel):
    problem_summary: str
    error_type: str | None
    category: str
    root_cause: str
    confidence: str
    reasoning: str
    reproduced: bool | None
    fixes: list[ReportFix]
    sources: list[Evidence]
    open_questions: list[str]
    warnings: list[str]
    steps: list[StepLog]
    revisions: int
    llm_calls: int
    duration_ms: int
    markdown: str = ""

from troubleshooter.agents.common import Stopwatch, describe_error, step
from troubleshooter.config import Settings
from troubleshooter.llm import StructuredLLM
from troubleshooter.schemas import TriagePlan
from troubleshooter.state import CODE_ANALYST, DOC_RESEARCHER, GITHUB_RESEARCHER, TRIAGE, GraphState
from troubleshooter.tools.static_analysis import number_lines
from troubleshooter.tools.traceback_parser import parse_traceback

SYSTEM_PROMPT = """You are the triage lead of a Python debugging team.
Read the developer's report and plan the investigation; do not try to solve the problem yet.

- search_queries target the documentation index: name the exception, the API involved and the suspected mechanism.
- Set analyze_code to true when code is provided and running or inspecting it could confirm the cause.
- Set search_github to true only when a third-party library, version incompatibility or packaging problem is plausible.
  Standard-library and plain language errors are covered by the documentation index."""


class TriageAgent:
    def __init__(self, llm: StructuredLLM, settings: Settings):
        self.llm = llm
        self.settings = settings

    def __call__(self, state: GraphState) -> dict:
        watch = Stopwatch()
        parsed = parse_traceback(state["query"])
        code = state.get("code")

        prompt = [f"Developer report:\n{state['query']}", f"Parsed error:\n{describe_error(parsed)}"]
        if code:
            prompt.append(f"Submitted code:\n{number_lines(code)}")
        plan = self.llm.generate(TriagePlan, SYSTEM_PROMPT, "\n\n".join(prompt), run_name="triage")

        if parsed.exception_type:
            plan.error_type = parsed.exception_type

        pending = [DOC_RESEARCHER]
        if code and plan.analyze_code:
            pending.append(CODE_ANALYST)
        if plan.search_github and self._github_allowed(state):
            pending.append(GITHUB_RESEARCHER)

        return {
            "parsed": parsed,
            "plan": plan,
            "pending": pending,
            "completed": [TRIAGE],
            "llm_calls": 1,
            "steps": step(
                TRIAGE,
                f"Classified as {plan.category.replace('_', ' ')}"
                + (f" ({plan.error_type})" if plan.error_type else "")
                + f"; planned: {', '.join(pending)}",
                watch,
                problem=plan.problem_summary,
                queries=plan.search_queries,
                rationale=plan.rationale,
                frames=len(parsed.frames),
            ),
        }

    def _github_allowed(self, state: GraphState) -> bool:
        return self.settings.enable_github_search and state.get("enable_github", True)

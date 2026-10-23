from troubleshooter.agents.common import Stopwatch, describe_error, step
from troubleshooter.config import Settings
from troubleshooter.llm import StructuredLLM
from troubleshooter.schemas import CodeFindings, Evidence, ExecutionResult, ParsedTraceback
from troubleshooter.state import CODE_ANALYST, GraphState
from troubleshooter.tools.sandbox import run_python
from troubleshooter.tools.static_analysis import analyze, number_lines

SYSTEM_PROMPT = """You are a senior Python engineer analysing code that fails.
You are given the code with line numbers, static analysis output and the result of running it in a
standard-library-only sandbox. Report facts you can point to in the code or the tool output.
Do not propose fixes; another engineer will do that."""


def describe_run(result: ExecutionResult) -> str:
    if result.timed_out:
        return "Timed out."
    output = [f"Exit code: {result.exit_code}"]
    if result.stdout.strip():
        output.append(f"stdout:\n{result.stdout.strip()}")
    if result.stderr.strip():
        output.append(f"stderr:\n{result.stderr.strip()}")
    return "\n".join(output)


def reproduces(reported: ParsedTraceback, run: ExecutionResult | None) -> bool | None:
    """Whether the sandbox run raised the exception the developer reported."""
    if run is None or not reported.found:
        return None
    return bool(run.exception and run.exception.exception_type == reported.exception_type)


class CodeAnalyst:
    def __init__(self, llm: StructuredLLM, settings: Settings):
        self.llm = llm
        self.settings = settings

    def __call__(self, state: GraphState) -> dict:
        watch = Stopwatch()
        code = state["code"] or ""
        static = analyze(code)
        run = run_python(code, self.settings.sandbox_timeout_s) if self.settings.enable_code_execution else None
        reproduced = reproduces(state["parsed"], run)

        prompt = [
            f"Problem: {state['plan'].problem_summary}",
            f"Reported error:\n{describe_error(state['parsed'])}",
            f"Code:\n{number_lines(code)}",
            f"Static analysis:\n{static.summary()}",
            f"Sandbox run:\n{describe_run(run) if run else 'Execution disabled.'}",
        ]
        findings = self.llm.generate(CodeFindings, SYSTEM_PROMPT, "\n\n".join(prompt), run_name="analyze_code")

        evidence = [
            Evidence(
                id="C1",
                kind="code_analysis",
                title="Static analysis of submitted code",
                source="ast + pyflakes",
                snippet=static.summary(),
            ),
            Evidence(
                id="C2",
                kind="code_analysis",
                title="Code analyst findings",
                source="code_analyst",
                snippet=self._format_findings(findings),
            ),
        ]
        if run:
            evidence.append(
                Evidence(
                    id="E1",
                    kind="execution",
                    title="Sandbox run of the original code",
                    source="sandbox",
                    snippet=describe_run(run),
                )
            )

        if reproduced is None:
            outcome = "no reported exception to reproduce" if run else "execution disabled"
        else:
            outcome = "reproduced the reported error" if reproduced else "did not reproduce the reported error"
        return {
            "code_findings": findings,
            "reproduction": run,
            "evidence": evidence,
            "completed": [CODE_ANALYST],
            "llm_calls": 1,
            "steps": step(
                CODE_ANALYST,
                f"Static analysis + sandbox run: {outcome}; suspect lines {findings.suspect_lines or 'none'}",
                watch,
                hypothesis=findings.hypothesis,
                pyflakes=static.pyflakes,
                exit_code=run.exit_code if run else None,
                reproduced=reproduced,
            ),
        }

    @staticmethod
    def _format_findings(findings: CodeFindings) -> str:
        lines = [f"Suspect lines: {findings.suspect_lines}", f"Hypothesis: {findings.hypothesis}"]
        lines.extend(f"- {obs}" for obs in findings.observations)
        return "\n".join(lines)

"""Check proposed fixes against the evidence and by execution.

A fix counts as verified only if the original code fails (raises, or fails the
fix's own assertions) and the patched code passes in the sandbox. Everything
else is labelled with the reason it could not be verified.
"""

from troubleshooter.agents.common import Stopwatch, step
from troubleshooter.config import Settings
from troubleshooter.schemas import Diagnosis, ExecutionResult, FixValidation, ProposedFix
from troubleshooter.state import VALIDATOR, GraphState
from troubleshooter.tools.sandbox import run_python

# Failures that depend on the machine rather than on the code under test.
ENVIRONMENTAL_ERRORS = {
    "ModuleNotFoundError",
    "ImportError",
    "FileNotFoundError",
    "PermissionError",
    "ConnectionError",
    "ConnectionRefusedError",
    "TimeoutError",
    "URLError",
    "gaierror",
    "OSError",
}


def _error_name(run: ExecutionResult) -> str | None:
    return run.exception.exception_type if run.exception else None


def _error_line(run: ExecutionResult) -> str:
    if run.timed_out:
        return "timed out"
    if run.exception and run.exception.exception_type:
        return f"{run.exception.exception_type}: {run.exception.message or ''}".strip()
    return f"exit code {run.exit_code}"


class Validator:
    def __init__(self, settings: Settings):
        self.settings = settings

    def __call__(self, state: GraphState) -> dict:
        watch = Stopwatch()
        diagnosis: Diagnosis = state["diagnosis"]
        evidence_ids = {item.id for item in state.get("evidence", [])}
        original = state.get("code")

        validations = [
            self.validate_fix(index, fix, original, evidence_ids, state.get("reproduction"))
            for index, fix in enumerate(diagnosis.fixes)
        ]
        counts = {
            status: sum(v.status == status for v in validations)
            for status in ("verified", "failed", "not_verifiable", "not_run")
        }
        summary = ", ".join(f"{n} {status.replace('_', ' ')}" for status, n in counts.items() if n)

        return {
            "validations": validations,
            "validated_round": state["diagnosis_round"],
            "feedback": self._feedback(diagnosis, validations),
            "steps": step(
                VALIDATOR,
                f"Checked {len(validations)} fix(es): {summary or 'nothing to check'}",
                watch,
                results=[
                    {"fix": diagnosis.fixes[v.fix_index].title, "status": v.status, "detail": v.detail}
                    for v in validations
                ],
            ),
        }

    def validate_fix(
        self,
        index: int,
        fix: ProposedFix,
        original: str | None,
        evidence_ids: set[str],
        reproduction: ExecutionResult | None,
    ) -> FixValidation:
        unknown = sorted(set(fix.citations) - evidence_ids)
        grounded = bool(fix.citations) and not unknown
        result = dict(fix_index=index, grounded=grounded, unknown_citations=unknown)

        if not fix.patched_code:
            return FixValidation(**result, status="not_run", detail="No code change proposed; nothing to execute.")
        if not original:
            return FixValidation(
                **result, status="not_run", detail="No original code was submitted to compare against."
            )
        if not self.settings.enable_code_execution:
            return FixValidation(**result, status="not_run", detail="Code execution is disabled.")

        timeout = self.settings.sandbox_timeout_s
        if fix.test_code:
            original_run = run_python(f"{original}\n\n{fix.test_code}\n", timeout)
            patched_run = run_python(f"{fix.patched_code}\n\n{fix.test_code}\n", timeout)
        else:
            original_run = reproduction or run_python(original, timeout)
            patched_run = run_python(fix.patched_code, timeout)
        result["patched_run"] = patched_run

        if not patched_run.succeeded:
            if _error_name(patched_run) in ENVIRONMENTAL_ERRORS:
                return FixValidation(
                    **result,
                    status="not_verifiable",
                    detail=f"Depends on the environment ({_error_line(patched_run)}); "
                    "the sandbox is standard-library only.",
                )
            return FixValidation(**result, status="failed", detail=f"Patched code failed: {_error_line(patched_run)}")

        if original_run.succeeded:
            return FixValidation(
                **result,
                status="not_verifiable",
                detail="Patched code runs, but so does the original, so execution cannot confirm the fix.",
            )

        if _error_name(original_run) in ENVIRONMENTAL_ERRORS:
            return FixValidation(
                **result,
                status="not_verifiable",
                detail=f"The original only failed for an environmental reason ({_error_line(original_run)}), "
                "so a passing patch does not confirm the root cause.",
            )

        check = "its assertions" if fix.test_code else "cleanly"
        return FixValidation(
            **result,
            status="verified",
            detail=f"Original failed ({_error_line(original_run)}); patched code ran {check}.",
        )

    @staticmethod
    def _feedback(diagnosis: Diagnosis, validations: list[FixValidation]) -> str | None:
        failures = []
        for v in validations:
            if v.status != "failed":
                continue
            fix = diagnosis.fixes[v.fix_index]
            stderr = v.patched_run.stderr.strip()[-1500:] if v.patched_run else ""
            failures.append(f"Fix '{fix.title}' failed in the sandbox: {v.detail}\n{stderr}")
        return "\n\n".join(failures) or None

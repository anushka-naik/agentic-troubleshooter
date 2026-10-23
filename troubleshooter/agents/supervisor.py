"""Deterministic supervisor.

The LLM decides *what* is worth investigating (the triage plan) and *what the
answer is* (the diagnosis). Control flow - ordering, escalation, the
revision budget and termination - is plain code, so every run is bounded and
each routing decision is explainable from state alone.
"""

from troubleshooter.agents.common import Stopwatch, step
from troubleshooter.config import Settings
from troubleshooter.state import (
    DIAGNOSTICIAN,
    GITHUB_RESEARCHER,
    REPORTER,
    SPECIALISTS,
    SUPERVISOR,
    VALIDATOR,
    GraphState,
)


class Supervisor:
    def __init__(self, settings: Settings):
        self.settings = settings

    def __call__(self, state: GraphState) -> dict:
        watch = Stopwatch()
        pending = list(state.get("pending", []))
        update: dict = {}

        if self._should_escalate_to_github(state, pending):
            pending.append(GITHUB_RESEARCHER)
            update["pending"] = pending

        next_step, reason = self._decide(state, pending)
        update["next_step"] = next_step
        update["steps"] = step(SUPERVISOR, f"Route to {next_step}: {reason}", watch, next=next_step)
        return update

    def _decide(self, state: GraphState, pending: list[str]) -> tuple[str, str]:
        completed = set(state.get("completed", []))

        for specialist in SPECIALISTS:
            if specialist in pending and specialist not in completed:
                return specialist, "planned investigation step"

        diagnosis_round = state.get("diagnosis_round", 0)
        if diagnosis_round == 0:
            return DIAGNOSTICIAN, "investigation complete, evidence ready for diagnosis"

        if state.get("validated_round", 0) < diagnosis_round:
            return VALIDATOR, "proposed fixes must be checked before reporting"

        if self._needs_revision(state):
            if diagnosis_round <= self.settings.max_revisions:
                return DIAGNOSTICIAN, "no fix passed validation, requesting a revision with execution feedback"
            return REPORTER, "revision budget exhausted, reporting unverified fixes"

        return REPORTER, "diagnosis validated"

    def _should_escalate_to_github(self, state: GraphState, pending: list[str]) -> bool:
        return (
            state.get("doc_coverage") == "insufficient"
            and GITHUB_RESEARCHER not in pending
            and self.settings.enable_github_search
            and state.get("enable_github", True)
        )

    @staticmethod
    def _needs_revision(state: GraphState) -> bool:
        statuses = {v.status for v in state.get("validations", [])}
        return "failed" in statuses and "verified" not in statuses

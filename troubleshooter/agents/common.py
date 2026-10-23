import time

from troubleshooter.schemas import Evidence, ParsedTraceback, StepLog


class Stopwatch:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)


def step(agent: str, summary: str, watch: Stopwatch, **details) -> list[StepLog]:
    return [StepLog(agent=agent, summary=summary, duration_ms=watch.ms, details=details)]


def describe_error(parsed: ParsedTraceback | None) -> str:
    if not parsed or not parsed.found:
        return "No exception was identified in the report."
    lines = [f"{parsed.exception_type}: {parsed.message or ''}".strip()]
    if parsed.exception_module:
        lines.append(f"Module: {parsed.exception_module}")
    for frame in parsed.frames[-3:]:
        lines.append(f"  at {frame.file}:{frame.line} in {frame.function}: {frame.source or ''}")
    for warning in parsed.warnings:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


def format_evidence(evidence: list[Evidence]) -> str:
    if not evidence:
        return "(no evidence collected)"
    blocks = [f"[{item.id}] {item.title} ({item.source})\n{item.snippet}" for item in evidence]
    return "\n\n".join(blocks)

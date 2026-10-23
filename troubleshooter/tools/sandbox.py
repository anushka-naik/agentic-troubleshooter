"""Run untrusted Python snippets in a constrained subprocess.

Isolation is best-effort and intended for a local or containerised demo:

* ``-I -S`` ignores PYTHON* variables, the user site directory and site-packages,
  so snippets see the standard library only and runs are reproducible.
* The process gets an empty environment, a throwaway working directory,
  CPU/memory/file-size limits and a wall-clock timeout.

It does not block network access. Run the service inside Docker (non-root) if
it is exposed to anyone else.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from langsmith import traceable

from troubleshooter.schemas import ExecutionResult
from troubleshooter.tools.traceback_parser import parse_traceback

_OUTPUT_LIMIT = 4_000
_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
_FILE_SIZE_LIMIT_BYTES = 1024 * 1024
_SCRIPT_NAME = "snippet.py"


def _limit_resources(cpu_seconds: int) -> None:
    import resource

    limits = [
        (resource.RLIMIT_CPU, cpu_seconds),
        (resource.RLIMIT_FSIZE, _FILE_SIZE_LIMIT_BYTES),
        (resource.RLIMIT_AS, _MEMORY_LIMIT_BYTES),
    ]
    for kind, value in limits:
        try:
            resource.setrlimit(kind, (value, value))
        except (ValueError, OSError):
            # macOS does not allow lowering RLIMIT_AS; the timeout still applies.
            pass


def _truncate(text: str) -> str:
    if len(text) <= _OUTPUT_LIMIT:
        return text
    return text[:_OUTPUT_LIMIT] + "\n... [truncated]"


@traceable(run_type="tool", name="sandbox.run_python")
def run_python(code: str, timeout_s: float = 5.0) -> ExecutionResult:
    preexec = None
    if os.name == "posix":
        cpu_seconds = max(1, int(timeout_s) + 1)
        preexec = lambda: _limit_resources(cpu_seconds)  # noqa: E731

    with tempfile.TemporaryDirectory(prefix="sandbox-") as workdir:
        script = Path(workdir) / _SCRIPT_NAME
        script.write_text(code, encoding="utf-8")
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", _SCRIPT_NAME],
                cwd=workdir,
                env={"PYTHONIOENCODING": "utf-8"},
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                preexec_fn=preexec,
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                exit_code=None,
                stdout=_truncate(_decode(exc.stdout)),
                stderr=_truncate(_decode(exc.stderr)),
                timed_out=True,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    stderr = _truncate(proc.stderr)
    parsed = parse_traceback(stderr) if stderr else None
    return ExecutionResult(
        exit_code=proc.returncode,
        stdout=_truncate(proc.stdout),
        stderr=stderr,
        timed_out=False,
        duration_ms=int((time.perf_counter() - started) * 1000),
        exception=parsed if parsed and (parsed.found or parsed.warnings) else None,
    )


def _decode(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value

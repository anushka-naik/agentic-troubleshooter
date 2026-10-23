import re

from troubleshooter.schemas import ParsedTraceback, StackFrame

_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\S+)')
_EXCEPTION = re.compile(
    r"(?<![\w.])(?P<qualname>(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*(?:Error|Exception|Warning|Interrupt|Exit|Iteration))"
    r"(?::[ \t]*(?P<message>[^\n]*))?"
)
_CARET_LINE = re.compile(r"^\s*[\^~\s]+$")
_MAX_MESSAGE = 300


def parse_traceback(text: str) -> ParsedTraceback:
    """Extract stack frames, the final exception and any warnings from free text.

    Works on full tracebacks as well as prose such as "I get TypeError: ...".
    The last non-warning exception wins because chained tracebacks print the
    original cause first and the exception that propagated last.
    """
    lines = text.splitlines()
    frames: list[StackFrame] = []
    for i, line in enumerate(lines):
        match = _FRAME.match(line)
        if not match:
            continue
        source = None
        if i + 1 < len(lines):
            candidate = lines[i + 1].strip()
            if candidate and not _FRAME.match(lines[i + 1]) and not _CARET_LINE.match(lines[i + 1]):
                source = candidate
        frames.append(
            StackFrame(
                file=match["file"],
                line=int(match["line"]),
                function=match["func"],
                source=source,
            )
        )

    exception_type = module = message = None
    warnings: list[str] = []
    for match in _EXCEPTION.finditer(text):
        qualname = match["qualname"]
        name = qualname.rsplit(".", 1)[-1]
        msg = (match["message"] or "").strip()[:_MAX_MESSAGE] or None
        if name.endswith("Warning"):
            warnings.append(f"{name}: {msg}" if msg else name)
            continue
        exception_type = name
        module = qualname.rsplit(".", 1)[0] if "." in qualname else None
        message = msg

    return ParsedTraceback(
        exception_type=exception_type,
        exception_module=module,
        message=message,
        frames=frames,
        warnings=warnings,
    )

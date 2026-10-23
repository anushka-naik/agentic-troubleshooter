import ast
from dataclasses import dataclass, field

from langsmith import traceable
from pyflakes.api import check
from pyflakes.reporter import Reporter


@dataclass
class StaticReport:
    syntax_ok: bool
    syntax_error: str | None = None
    pyflakes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = ["Syntax: OK" if self.syntax_ok else f"Syntax error: {self.syntax_error}"]
        if self.imports:
            parts.append("Imports: " + ", ".join(self.imports))
        if self.functions:
            parts.append("Functions: " + ", ".join(self.functions))
        if self.pyflakes:
            parts.append("Pyflakes:\n" + "\n".join(f"- {msg}" for msg in self.pyflakes))
        else:
            parts.append("Pyflakes: no findings")
        return "\n".join(parts)


class _CollectingReporter(Reporter):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def unexpectedError(self, filename, msg):  # noqa: N802 (pyflakes API)
        self.messages.append(str(msg))

    def syntaxError(self, filename, msg, lineno, offset, text):  # noqa: N802
        self.messages.append(f"line {lineno}: {msg}")

    def flake(self, message):
        self.messages.append(f"line {message.lineno}: {message.message % message.message_args}")


@traceable(run_type="tool", name="static_analysis")
def analyze(code: str) -> StaticReport:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return StaticReport(syntax_ok=False, syntax_error=f"line {exc.lineno}: {exc.msg}")

    imports: list[str] = []
    functions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            functions.append(f"{prefix}{node.name} (line {node.lineno})")

    reporter = _CollectingReporter()
    check(code, "snippet.py", reporter)
    return StaticReport(syntax_ok=True, pyflakes=reporter.messages, imports=imports, functions=functions)


def number_lines(code: str) -> str:
    return "\n".join(f"{i:>3} | {line}" for i, line in enumerate(code.splitlines(), start=1))

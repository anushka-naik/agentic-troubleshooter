import pytest
from conftest import NONE_SORT_QUERY

from troubleshooter.rag.retriever import tokenize
from troubleshooter.tools.sandbox import run_python
from troubleshooter.tools.static_analysis import analyze
from troubleshooter.tools.traceback_parser import parse_traceback


def test_parses_full_traceback():
    parsed = parse_traceback(NONE_SORT_QUERY)
    assert parsed.exception_type == "TypeError"
    assert parsed.message == "'NoneType' object is not subscriptable"
    assert [f.line for f in parsed.frames] == [6, 3]
    assert parsed.frames[-1].source == "return ranked[:3]"


def test_parses_qualified_exception_in_prose():
    parsed = parse_traceback("It fails with json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)")
    assert parsed.exception_type == "JSONDecodeError"
    assert parsed.exception_module == "json.decoder"


def test_separates_warnings_from_exceptions():
    parsed = parse_traceback(
        "TypeError: 'coroutine' object is not subscriptable\nRuntimeWarning: coroutine 'f' was never awaited"
    )
    assert parsed.exception_type == "TypeError"
    assert parsed.warnings == ["RuntimeWarning: coroutine 'f' was never awaited"]


def test_no_exception_in_plain_question():
    assert not parse_traceback("Why does my default list keep growing?").found


def test_sandbox_captures_exception():
    result = run_python("items = [3, 1]\nprint(items.sort()[0])\n")
    assert result.exit_code == 1
    assert result.exception.exception_type == "TypeError"


def test_sandbox_success_and_stdout():
    result = run_python("print(sorted([3, 1, 2]))")
    assert result.succeeded
    assert result.stdout.strip() == "[1, 2, 3]"


def test_sandbox_timeout():
    result = run_python("while True:\n    pass\n", timeout_s=1)
    assert result.timed_out and not result.succeeded


def test_sandbox_is_stdlib_only():
    result = run_python("import pydantic\n")
    assert result.exception.exception_type == "ModuleNotFoundError"


def test_static_analysis_reports_undefined_names():
    report = analyze("def f():\n    return missing_name\n")
    assert report.syntax_ok
    assert any("undefined name 'missing_name'" in msg for msg in report.pyflakes)


def test_static_analysis_reports_syntax_error():
    report = analyze("def f(:\n")
    assert not report.syntax_ok


def test_tokenizer_keeps_identifiers():
    assert tokenize("TypeError: 'NoneType' object") == ["typeerror", "nonetype", "object"]


@pytest.mark.parametrize(
    "queries, expected_doc",
    [
        (["'NoneType' object is not subscriptable list.sort"], "none_and_in_place_methods"),
        (["dictionary changed size during iteration"], "dict_iteration_mutation"),
        (["why does my default list keep growing between calls"], "mutable_default_arguments"),
        (["coroutine was never awaited"], "asyncio_coroutines"),
    ],
)
def test_retrieval_top_hit(retriever, queries, expected_doc):
    assert retriever.search(queries, k=3)[0].chunk_id.startswith(expected_doc)

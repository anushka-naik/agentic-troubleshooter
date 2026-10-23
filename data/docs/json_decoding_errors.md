# JSON Decoding Errors

Source: https://docs.python.org/3/library/json.html#json.JSONDecodeError

## json.JSONDecodeError

`json.loads()` and `json.load()` raise `json.JSONDecodeError` when the input is not a valid JSON document. It is a subclass of `ValueError` and exposes the attributes `msg`, `doc`, `pos`, `lineno` and `colno`, which identify where parsing failed.

## "Expecting value: line 1 column 1 (char 0)"

```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

This message means the parser found nothing that starts a JSON value at the very first character. The most common causes are:

- The input is an empty string. HTTP responses with status 204 (No Content), failed requests, or empty files all produce `""`.
- The input is HTML or plain text, for example an error page from a proxy or a login redirect.
- The input starts with a byte order mark or other leading characters.
- The input is a Python literal such as `None` or `{'a': 1}` with single quotes, which is not valid JSON.

## Diagnosing

Log the raw payload (or its first few hundred characters) and its type before decoding. When the data comes from an HTTP client, check the status code and the `Content-Type` header before calling the JSON decoder.

## Fixes

Guard against empty input and decide explicitly what an empty payload means for the caller:

```python
import json

def parse_payload(raw):
    if not raw or not raw.strip():
        return {}
    return json.loads(raw)
```

Catch the specific exception when malformed input is expected and should be handled gracefully:

```python
try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    logger.warning("Invalid JSON at line %s column %s: %s", exc.lineno, exc.colno, exc.msg)
    data = None
```

Avoid catching a bare `Exception` around JSON parsing, which hides unrelated bugs.

## Other common messages

- `Expecting property name enclosed in double quotes`: keys use single quotes or there is a trailing comma.
- `Extra data: line 1 column N`: more than one JSON document in the string, as in JSON Lines files. Parse line by line instead.
- `Unterminated string starting at`: the payload was truncated, often by a size limit or a partial read.

## Serialisation errors

`TypeError: Object of type datetime is not JSON serializable` occurs on `json.dumps()` for types the encoder does not support. Convert values first (for example with `isoformat()`) or pass a `default=` callable.

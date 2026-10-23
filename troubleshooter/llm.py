"""Thin structured-output interface over the chat model.

Agents depend on the ``StructuredLLM`` protocol rather than on a provider SDK,
which keeps the graph testable with a scripted model and makes the provider a
configuration detail.
"""

import logging
import re
import time
from typing import Protocol, TypeVar

import openai
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from troubleshooter.config import Settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

_RETRY_HINT = re.compile(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)")
_MAX_RATE_LIMIT_WAITS = 6
_MAX_WAIT_S = 65.0
_MAX_SCHEMA_REPAIRS = 2


def _schema_error(error: openai.BadRequestError) -> str | None:
    """Validation message when the provider rejected output that broke the schema.

    Providers that validate after generation (Groq) return 400 json_validate_failed
    instead of constraining decoding, so the call is retried with the error as feedback.
    """
    body = error.body if isinstance(error.body, dict) else {}
    details = body.get("error", body)
    if details.get("code") != "json_validate_failed":
        return None
    return details.get("message", "output did not match the schema")


def _retry_delay(error: openai.RateLimitError) -> float | None:
    """Seconds to wait from a tokens-per-minute 429, or None if waiting will not help
    (for example an exhausted credit balance)."""
    match = _RETRY_HINT.search(str(error))
    if not match:
        return None
    minutes, value, unit = match.groups()
    seconds = float(value) / 1000 if unit == "ms" else float(value)
    return min(int(minutes or 0) * 60 + seconds + 1.0, _MAX_WAIT_S)


class LLMUnavailableError(RuntimeError):
    pass


class StructuredLLM(Protocol):
    name: str

    def generate(self, schema: type[T], system: str, user: str, *, run_name: str) -> T: ...


class ChatStructuredLLM:
    def __init__(self, settings: Settings):
        if not settings.llm_configured:
            raise LLMUnavailableError(f"{settings.llm_key_name} is not set. Add it to .env to run investigations.")

        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": settings.llm_model,
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url,
            "timeout": settings.llm_timeout_s,
            "max_retries": 2,
        }
        if settings.llm_reasoning_effort:
            kwargs["reasoning_effort"] = settings.llm_reasoning_effort
        if settings.llm_temperature is not None:
            kwargs["temperature"] = settings.llm_temperature
        self._chat = ChatOpenAI(**kwargs)
        self.name = settings.llm_model

    def generate(self, schema: type[T], system: str, user: str, *, run_name: str) -> T:
        runnable = self._chat.with_structured_output(schema, method="json_schema", strict=True)
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        waits = repairs = 0
        while True:
            try:
                result = runnable.invoke(messages, config={"run_name": run_name})
                break
            except openai.RateLimitError as exc:
                delay = _retry_delay(exc)
                if delay is None or waits == _MAX_RATE_LIMIT_WAITS:
                    raise
                waits += 1
                logger.warning("%s: rate limited, waiting %.1fs", run_name, delay)
                time.sleep(delay)
            except openai.BadRequestError as exc:
                problem = _schema_error(exc)
                if problem is None or repairs == _MAX_SCHEMA_REPAIRS:
                    raise
                repairs += 1
                logger.warning("%s: output failed schema validation, retrying", run_name)
                fields = ", ".join(schema.model_fields)
                messages = [
                    SystemMessage(content=system),
                    HumanMessage(
                        content=f"{user}\n\nYour previous answer was rejected: {problem}\n"
                        f"Return a JSON object containing every field: {fields}."
                    ),
                ]
        if result is None:
            raise RuntimeError(f"{run_name}: model returned no structured output")
        return result


class LazyChatLLM:
    """Defers client construction until the first call, so the service can
    start, index documents and serve the UI before a key is configured."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: ChatStructuredLLM | None = None
        self.name = settings.llm_model

    def generate(self, schema: type[T], system: str, user: str, *, run_name: str) -> T:
        if self._client is None:
            self._client = ChatStructuredLLM(self._settings)
        return self._client.generate(schema, system, user, run_name=run_name)

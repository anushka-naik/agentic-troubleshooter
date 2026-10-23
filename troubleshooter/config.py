from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# LangSmith and the model clients read their configuration from os.environ,
# so the .env file is exported to the process environment, not just parsed.
load_dotenv(PROJECT_ROOT / ".env")

PROVIDER_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "xai": "https://api.x.ai/v1",
    "openai": None,
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # All providers expose an OpenAI-compatible API; the provider selects
    # the key, model and base URL used by the chat client.
    llm_provider: Literal["groq", "xai", "openai"] = "groq"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    xai_api_key: str | None = None
    xai_model: str = "grok-4"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    llm_temperature: float | None = 0.0
    llm_reasoning_effort: Literal["low", "medium", "high"] | None = None
    llm_timeout_s: float = 60.0

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: Path = PROJECT_ROOT / ".cache" / "fastembed"
    docs_dir: Path = PROJECT_ROOT / "data" / "docs"
    index_dir: Path = PROJECT_ROOT / "data" / "index"
    scenarios_path: Path = PROJECT_ROOT / "data" / "scenarios.json"

    retrieval_k: int = 8
    min_relevant_chunks: int = 2

    enable_github_search: bool = True
    github_token: str | None = None

    enable_code_execution: bool = True
    sandbox_timeout_s: float = 5.0
    max_revisions: int = 1

    @field_validator("llm_temperature", "llm_reasoning_effort", mode="before")
    @classmethod
    def _optional_temperature(cls, value):
        # Reasoning models reject a temperature; LLM_TEMPERATURE=none omits it.
        if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
            return None
        return value

    @property
    def llm_api_key(self) -> str | None:
        return getattr(self, f"{self.llm_provider}_api_key")

    @property
    def llm_model(self) -> str:
        return getattr(self, f"{self.llm_provider}_model")

    @property
    def llm_base_url(self) -> str | None:
        return PROVIDER_BASE_URLS[self.llm_provider]

    @property
    def llm_key_name(self) -> str:
        return f"{self.llm_provider.upper()}_API_KEY"

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()

import json
import time
import uuid
from collections.abc import Iterator

from troubleshooter.config import Settings
from troubleshooter.graph import build_graph
from troubleshooter.llm import LazyChatLLM, StructuredLLM
from troubleshooter.rag.retriever import HybridRetriever
from troubleshooter.schemas import Report, TroubleshootRequest

RECURSION_LIMIT = 30


class TroubleshootService:
    """Owns the long-lived resources: the index, the model client and the compiled graph."""

    def __init__(self, settings: Settings, llm: StructuredLLM | None = None, retriever: HybridRetriever | None = None):
        self.settings = settings
        self.llm = llm or LazyChatLLM(settings)
        self.retriever = retriever or HybridRetriever.from_settings(settings)
        self.graph = build_graph(self.llm, self.retriever, settings)

    def _inputs(self, request: TroubleshootRequest) -> dict:
        return {
            "query": request.query,
            "code": request.code or None,
            "enable_github": request.enable_github,
            "started_at": time.time(),
        }

    def _config(self, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "run_name": "troubleshoot",
            "tags": ["agentic"],
            "metadata": {"model": self.llm.name},
            "recursion_limit": RECURSION_LIMIT,
        }

    def run(self, request: TroubleshootRequest) -> Report:
        state = self.graph.invoke(self._inputs(request), config=self._config(str(uuid.uuid4())))
        return state["report"]

    def stream(self, request: TroubleshootRequest) -> Iterator[dict]:
        """Yield one event per agent step as it completes, then the final report."""
        run_id = str(uuid.uuid4())
        yield {"event": "start", "data": {"run_id": run_id}}
        for update in self.graph.stream(self._inputs(request), config=self._config(run_id), stream_mode="updates"):
            for node, delta in update.items():
                if not delta:
                    continue
                for log in delta.get("steps", []):
                    yield {"event": "step", "data": {"node": node, **log.model_dump()}}
                if "report" in delta:
                    yield {"event": "report", "data": delta["report"].model_dump()}

    def mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()


def to_sse(event: dict) -> str:
    return f"event: {event['event']}\ndata: {json.dumps(event['data'], default=str)}\n\n"

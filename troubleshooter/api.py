import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from troubleshooter.config import get_settings
from troubleshooter.schemas import Report, TroubleshootRequest
from troubleshooter.service import TroubleshootService, to_sse

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.service = TroubleshootService(get_settings())
    yield


app = FastAPI(title="Agentic Troubleshooter", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def _service(request: Request) -> TroubleshootService:
    return request.app.state.service


def _require_llm(service: TroubleshootService) -> None:
    if not service.settings.llm_configured:
        key = service.settings.llm_key_name
        raise HTTPException(status_code=503, detail=f"{key} is not set. Add it to .env and restart.")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health(request: Request) -> dict:
    service = _service(request)
    settings = service.settings
    return {
        "status": "ok",
        "llm_configured": settings.llm_configured,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "api_key_name": settings.llm_key_name,
        "indexed_chunks": service.retriever.size,
        "code_execution": settings.enable_code_execution,
        "github_search": settings.enable_github_search,
        "langsmith_tracing": os.getenv("LANGSMITH_TRACING", "").lower() == "true",
    }


@app.get("/api/scenarios")
def scenarios(request: Request) -> list[dict]:
    raw = json.loads(_service(request).settings.scenarios_path.read_text(encoding="utf-8"))
    return [{key: item[key] for key in ("id", "title", "query", "code")} for item in raw]


@app.get("/api/graph")
def graph(request: Request) -> dict:
    return {"mermaid": _service(request).mermaid()}


@app.post("/api/troubleshoot", response_model=Report)
def troubleshoot(body: TroubleshootRequest, request: Request) -> Report:
    service = _service(request)
    _require_llm(service)
    return service.run(body)


@app.post("/api/troubleshoot/stream")
def troubleshoot_stream(body: TroubleshootRequest, request: Request) -> StreamingResponse:
    service = _service(request)
    _require_llm(service)

    def events():
        try:
            for event in service.stream(body):
                yield to_sse(event)
        except Exception as exc:
            logger.exception("Investigation failed")
            yield to_sse({"event": "error", "data": {"message": f"{type(exc).__name__}: {exc}"}})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

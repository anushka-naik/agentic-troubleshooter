import json

import pytest
from conftest import FINDINGS, FIXED_CODE, NONE_SORT_CODE, NONE_SORT_QUERY, ScriptedLLM, diagnosis, grade_all, plan
from fastapi.testclient import TestClient

from troubleshooter.api import app
from troubleshooter.schemas import CodeFindings, Diagnosis, RelevanceGrades, TriagePlan
from troubleshooter.service import TroubleshootService


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def use_scripted_service(client, settings, retriever):
    llm = ScriptedLLM(
        {TriagePlan: plan(), RelevanceGrades: grade_all, CodeFindings: FINDINGS, Diagnosis: diagnosis(FIXED_CODE)}
    )
    configured = settings.model_copy(update={"llm_provider": "groq", "groq_api_key": "test"})
    client.app.state.service = TroubleshootService(configured, llm=llm, retriever=retriever)


def test_health_and_metadata(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["indexed_chunks"] > 0

    scenarios = client.get("/api/scenarios").json()
    assert {"id", "title", "query", "code"} == set(scenarios[0])

    assert "supervisor" in client.get("/api/graph").json()["mermaid"]


def test_requires_api_key(client, settings, retriever):
    unconfigured = settings.model_copy(update={"llm_provider": "groq", "groq_api_key": None})
    client.app.state.service = TroubleshootService(unconfigured, retriever=retriever)
    response = client.post("/api/troubleshoot", json={"query": NONE_SORT_QUERY})
    assert response.status_code == 503


def test_rejects_invalid_request(client):
    assert client.post("/api/troubleshoot", json={"query": ""}).status_code == 422


def test_stream_returns_report(client, settings, retriever):
    use_scripted_service(client, settings, retriever)
    response = client.post("/api/troubleshoot/stream", json={"query": NONE_SORT_QUERY, "code": NONE_SORT_CODE})
    assert response.status_code == 200

    events = [block for block in response.text.split("\n\n") if block]
    assert events[0].startswith("event: start")
    last = events[-1].splitlines()
    assert last[0] == "event: report"
    report = json.loads(last[1].removeprefix("data: "))
    assert report["fixes"][0]["validation"]["status"] == "verified"

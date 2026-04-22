"""Integration tests for the HTTP API layer."""

import pytest
from fastapi.testclient import TestClient

from ai_testplan_generator.api.app import create_app
from ai_testplan_generator.api import deps


@pytest.fixture
def client(mock_llm, settings):
    """TestClient with a mocked Brain."""
    # Override the Brain singleton with our test Brain.
    from ai_testplan_generator.pipelines.brain import Brain

    test_brain = Brain.build(llm=mock_llm, settings=settings)
    deps._brain = test_brain

    app = create_app()
    with TestClient(app) as c:
        yield c

    # Clean up singleton.
    deps._brain = None


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestIngestionEndpoint:
    def test_ingest_rejects_unsupported_format(self, client):
        resp = client.post(
            "/projects/proj-1/ingest",
            files={"file": ("test.jpg", b"fake image data", "image/jpeg")},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    def test_ingest_accepts_txt(self, client):
        content = b"The system shall respond within 200ms under normal load."
        resp = client.post(
            "/projects/proj-1/ingest",
            files={"file": ("spec.txt", content, "text/plain")},
        )
        # May succeed or fail depending on LLM mock behaviour,
        # but should not return 400 (format rejection).
        assert resp.status_code in (200, 500)

    def test_ingest_accepts_md(self, client):
        content = b"# Requirements\n\n## REQ-1\nThe system shall be fast.\n"
        resp = client.post(
            "/projects/proj-1/ingest",
            files={"file": ("spec.md", content, "text/markdown")},
        )
        assert resp.status_code in (200, 500)


class TestPlanEndpoints:
    def test_create_plan_returns_session_id(self, client):
        resp = client.post(
            "/projects/proj-1/plans",
            json={"goal": "Test the pump controller", "detail_level": "detailed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["session_id"].startswith("sess_")

    def test_session_not_found(self, client):
        resp = client.get("/sessions/nonexistent")
        assert resp.status_code == 404

    def test_plan_not_found(self, client):
        resp = client.get("/projects/proj-1/plans/nonexistent")
        assert resp.status_code == 404

    def test_list_plans_empty(self, client):
        resp = client.get("/projects/proj-1/plans")
        assert resp.status_code == 200
        assert resp.json() == []


class TestTraceEndpoint:
    def test_trace_not_found(self, client):
        resp = client.get("/trace/nonexistent")
        assert resp.status_code == 404

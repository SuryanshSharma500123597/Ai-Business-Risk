"""Health endpoint tests (frozen contract: docs/01_architecture/api.md §2)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_health_endpoint_ok() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] is True
    assert body["llm"] == "not_configured"  # no provider keys in test env
    assert body["version"] == "0.1.0"


def test_openapi_document_generated() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]

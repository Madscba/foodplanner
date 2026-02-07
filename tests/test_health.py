"""Tests for health check endpoints."""

from fastapi.testclient import TestClient

from foodplanner.main import app


def test_health_check() -> None:
    """Test basic health check endpoint."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "foodplanner-api"}


def test_root_endpoint() -> None:
    """Test root endpoint returns API info."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Foodplanner API"
    assert "version" in data
    assert data["docs"] == "/docs"

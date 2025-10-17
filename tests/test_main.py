"""Main application tests."""

from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient):
    """Test root endpoint returns service information."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "EDD Cloud Run Backend Resource API"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"


def test_api_info_endpoint(client: TestClient):
    """Test API info endpoint."""
    response = client.get("/api/v1/info")
    assert response.status_code == 200
    data = response.json()
    assert data["api_name"] == "EDD Cloud Run Backend Resource API"
    assert data["version"] == "1.0.0"
    assert "endpoints" in data
    assert "/api/v1/health" in data["endpoints"].values()


def test_docs_available(client: TestClient):
    """Test Swagger UI documentation is available."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_available(client: TestClient):
    """Test ReDoc documentation is available."""
    response = client.get("/redoc")
    assert response.status_code == 200

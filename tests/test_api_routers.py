"""API router tests."""

import io

from fastapi.testclient import TestClient


def test_gemini_health(client: TestClient):
    """Test Gemini API health check."""
    response = client.get("/api/v1/gemini/health")
    # 503 if API not configured, 200 if configured
    assert response.status_code in [200, 503]


def test_vision_health(client: TestClient):
    """Test Vision API health check."""
    response = client.get("/api/v1/vision/health")
    # 503 if API not configured, 200 if configured
    assert response.status_code in [200, 503]


def test_gemini_analyze_missing_file(client: TestClient):
    """Test Gemini analyze endpoint with missing file."""
    response = client.post(
        "/api/v1/gemini/analyze",
        data={"prompt": "Test prompt"},
    )
    assert response.status_code == 422  # Unprocessable Entity


def test_gemini_analyze_invalid_file_type(client: TestClient):
    """Test Gemini analyze endpoint with invalid file type."""
    response = client.post(
        "/api/v1/gemini/analyze",
        data={"prompt": "Test prompt"},
        files={"file": ("test.txt", io.BytesIO(b"not an image"), "text/plain")},
    )
    assert response.status_code == 400
    assert "画像ファイルのみ" in response.json()["detail"]


def test_gemini_analyze_empty_prompt(client: TestClient):
    """Test Gemini analyze endpoint with empty prompt."""
    response = client.post(
        "/api/v1/gemini/analyze",
        data={"prompt": "   "},
        files={"file": ("test.jpg", io.BytesIO(b"fake image data"), "image/jpeg")},
    )
    assert response.status_code == 400
    assert "プロンプトが空" in response.json()["detail"]


def test_vision_web_detection_missing_images(client: TestClient):
    """Test Vision web detection with missing images."""
    response = client.post(
        "/api/v1/vision/web-detection",
        json={"images": []},
    )
    assert response.status_code == 422  # Validation error

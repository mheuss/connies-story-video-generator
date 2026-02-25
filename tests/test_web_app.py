"""Tests for story_video.web.app — FastAPI application setup."""

from fastapi.testclient import TestClient

from story_video.web.app import create_app


class TestAppSetup:
    """Application factory and health endpoint."""

    def test_health_endpoint(self):
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_app_has_api_v1_prefix(self):
        app = create_app()
        client = TestClient(app)
        # Non-prefixed path should 404
        response = client.get("/health")
        assert response.status_code == 404

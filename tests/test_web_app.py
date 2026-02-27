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


class TestStaticFileServing:
    """Static file serving and SPA catch-all route."""

    def test_no_static_dir_root_404(self):
        """No static_dir means API-only mode; root path returns 404."""
        app = create_app()
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 404

    def test_with_static_dir_root_serves_index(self, tmp_path):
        """With static_dir, GET / serves index.html content."""
        index = tmp_path / "index.html"
        index.write_text("<html><body>Hello SPA</body></html>")
        (tmp_path / "assets").mkdir()

        app = create_app(static_dir=tmp_path)
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        assert "Hello SPA" in response.text

    def test_spa_fallback_serves_index(self, tmp_path):
        """Unknown paths like /projects/foo serve index.html for SPA routing."""
        index = tmp_path / "index.html"
        index.write_text("<html><body>SPA Fallback</body></html>")
        (tmp_path / "assets").mkdir()

        app = create_app(static_dir=tmp_path)
        client = TestClient(app)
        response = client.get("/projects/foo")
        assert response.status_code == 200
        assert "SPA Fallback" in response.text

    def test_api_routes_not_shadowed(self, tmp_path):
        """API routes still work when static_dir is set."""
        index = tmp_path / "index.html"
        index.write_text("<html><body>Index</body></html>")
        (tmp_path / "assets").mkdir()

        app = create_app(static_dir=tmp_path)
        client = TestClient(app)
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_nonexistent_static_dir_ignored(self, tmp_path):
        """Nonexistent static_dir is ignored; API works, root 404s."""
        nonexistent = tmp_path / "does-not-exist"

        app = create_app(static_dir=nonexistent)
        client = TestClient(app)

        # API still works
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Root path 404s since static dir doesn't exist
        response = client.get("/")
        assert response.status_code == 404

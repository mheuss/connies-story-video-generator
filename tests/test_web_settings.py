"""Tests for story_video.web.routes_settings -- API key management."""

import os

from fastapi.testclient import TestClient

from story_video.web.app import create_app


class TestGetApiKeyStatus:
    """GET /api/v1/settings/api-keys returns which keys are configured."""

    def test_returns_key_status_when_all_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/settings/api-keys")
        assert response.status_code == 200
        data = response.json()
        assert data["anthropic_configured"] is True
        assert data["openai_configured"] is True
        assert data["elevenlabs_configured"] is True

    def test_returns_false_when_keys_missing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        app = create_app(env_path=tmp_path / ".env")
        client = TestClient(app)
        response = client.get("/api/v1/settings/api-keys")
        assert response.status_code == 200
        data = response.json()
        assert data["anthropic_configured"] is False
        assert data["openai_configured"] is False
        assert data["elevenlabs_configured"] is False


class TestSetApiKeys:
    """POST /api/v1/settings/api-keys writes keys to .env and loads them."""

    def test_sets_keys_and_writes_env_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        env_path = tmp_path / ".env"
        app = create_app(env_path=env_path)
        client = TestClient(app)
        response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "anthropic_api_key": "sk-ant-new",
                "openai_api_key": "sk-new",
            },
        )
        assert response.status_code == 200
        # Keys are now in environment
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-new"
        assert os.environ.get("OPENAI_API_KEY") == "sk-new"
        # .env file was written
        assert env_path.exists()
        content = env_path.read_text()
        assert "ANTHROPIC_API_KEY=sk-ant-new" in content
        assert "OPENAI_API_KEY=sk-new" in content

    def test_partial_update_preserves_existing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-existing")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        env_path = tmp_path / ".env"
        app = create_app(env_path=env_path)
        client = TestClient(app)
        response = client.post(
            "/api/v1/settings/api-keys",
            json={"openai_api_key": "sk-new"},
        )
        assert response.status_code == 200
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-existing"
        assert os.environ.get("OPENAI_API_KEY") == "sk-new"

    def test_rejects_empty_key_values(self, tmp_path):
        env_path = tmp_path / ".env"
        app = create_app(env_path=env_path)
        client = TestClient(app)
        response = client.post(
            "/api/v1/settings/api-keys",
            json={"anthropic_api_key": "  "},
        )
        assert response.status_code == 422

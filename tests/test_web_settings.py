"""Tests for story_video.web.routes_settings -- API key management."""

import os

import pytest
from fastapi.testclient import TestClient

from story_video.web.app import create_app


class TestGetApiKeyStatus:
    """GET /api/v1/settings/api-keys returns which keys are configured."""

    @pytest.fixture(autouse=True)
    def _clean_managed_keys(self, monkeypatch):
        """Ensure managed API keys are cleaned up after each test."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

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

    def test_returns_false_when_keys_missing(self, tmp_path):
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

    @pytest.fixture(autouse=True)
    def _clean_managed_keys(self, monkeypatch):
        """Ensure managed API keys are cleaned up after each test."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    def test_sets_keys_and_writes_env_file(self, tmp_path):
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
        assert 'ANTHROPIC_API_KEY="sk-ant-new"' in content
        assert 'OPENAI_API_KEY="sk-new"' in content

    def test_partial_update_preserves_existing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-existing")
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

    def test_rejects_control_characters_in_key(self, tmp_path):
        """Keys with newlines are rejected to prevent .env injection."""
        env_path = tmp_path / ".env"
        app = create_app(env_path=env_path)
        client = TestClient(app)
        response = client.post(
            "/api/v1/settings/api-keys",
            json={"anthropic_api_key": "sk-ant-test\nEVIL_VAR=injected"},
        )
        assert response.status_code == 422

    def test_env_values_are_quoted(self, tmp_path):
        """Values in .env file are wrapped in double quotes."""
        env_path = tmp_path / ".env"
        app = create_app(env_path=env_path)
        client = TestClient(app)
        client.post(
            "/api/v1/settings/api-keys",
            json={"anthropic_api_key": "sk-ant-test"},
        )
        content = env_path.read_text()
        assert 'ANTHROPIC_API_KEY="sk-ant-test"' in content

    def test_rejects_no_keys_provided(self, tmp_path):
        """Empty request body is rejected with 422."""
        env_path = tmp_path / ".env"
        app = create_app(env_path=env_path)
        client = TestClient(app)
        response = client.post("/api/v1/settings/api-keys", json={})
        assert response.status_code == 422

    def test_preserves_unmanaged_env_content(self, tmp_path):
        """Setting API keys preserves comments and non-API-key variables."""
        env_path = tmp_path / ".env"
        env_path.write_text('# My comment\nDEBUG=1\nANTHROPIC_API_KEY="old"\n', encoding="utf-8")
        app = create_app(env_path=env_path)
        client = TestClient(app)
        client.post("/api/v1/settings/api-keys", json={"anthropic_api_key": "sk-new"})
        content = env_path.read_text()
        assert "# My comment" in content
        assert "DEBUG=1" in content
        assert 'ANTHROPIC_API_KEY="sk-new"' in content

    def test_removes_unset_managed_key(self, monkeypatch, tmp_path):
        """A managed key with empty env value is removed from the file."""
        env_path = tmp_path / ".env"
        env_path.write_text('ANTHROPIC_API_KEY="old"\nDEBUG=1\n', encoding="utf-8")
        app = create_app(env_path=env_path)
        # create_app loads .env via load_dotenv, restoring ANTHROPIC_API_KEY.
        # Remove it again to simulate the user clearing the key.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = TestClient(app)
        client.post("/api/v1/settings/api-keys", json={"openai_api_key": "sk-new"})
        content = env_path.read_text()
        assert "ANTHROPIC_API_KEY" not in content
        assert "DEBUG=1" in content
        assert 'OPENAI_API_KEY="sk-new"' in content

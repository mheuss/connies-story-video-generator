"""Tests for the 'serve' CLI command."""

from unittest.mock import patch

from typer.testing import CliRunner

from story_video.cli import app

_WEB_APP_MODULE = "story_video.web.app"

runner = CliRunner()


class TestServeCommand:
    """story-video serve starts the web server."""

    @patch("story_video.cli.uvicorn_run")
    def test_serve_default_port(self, mock_uvicorn):
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        mock_uvicorn.assert_called_once()
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs["port"] == 8033

    @patch("story_video.cli.uvicorn_run")
    def test_serve_custom_port(self, mock_uvicorn):
        result = runner.invoke(app, ["serve", "--port", "9000"])
        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs["port"] == 9000

    @patch("story_video.cli.uvicorn_run")
    def test_serve_custom_host(self, mock_uvicorn):
        result = runner.invoke(app, ["serve", "--host", "0.0.0.0"])
        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs["host"] == "0.0.0.0"

    @patch("story_video.cli.uvicorn_run")
    def test_port_env_var(self, mock_uvicorn, monkeypatch):
        monkeypatch.setenv("PORT", "9000")
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs["port"] == 9000

    @patch("story_video.cli.uvicorn_run")
    def test_cli_port_overrides_env_var(self, mock_uvicorn, monkeypatch):
        monkeypatch.setenv("PORT", "9000")
        result = runner.invoke(app, ["serve", "--port", "7777"])
        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs["port"] == 7777

    @patch("story_video.cli.uvicorn_run")
    def test_invalid_port_env_var_shows_error(self, mock_uvicorn, monkeypatch):
        """Non-numeric PORT env var shows clean error instead of traceback."""
        monkeypatch.setenv("PORT", "abc")
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 1
        assert "Invalid PORT" in result.output

    @patch("story_video.cli.uvicorn_run", None)
    def test_serve_without_web_deps_shows_error(self):
        """When uvicorn is not installed, shows install instructions and exits 1."""
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 1
        assert "Web dependencies not installed" in result.output


class TestStaticDirAutoDetect:
    """serve command auto-detects web/dist/ for static file serving."""

    @patch("story_video.cli.uvicorn_run")
    @patch(f"{_WEB_APP_MODULE}.create_app")
    def test_static_dir_detected_when_build_exists(
        self, mock_create_app, mock_uvicorn, tmp_path, monkeypatch
    ):
        """When web/dist/index.html exists, create_app receives static_dir."""
        dist_dir = tmp_path / "web" / "dist"
        dist_dir.mkdir(parents=True)
        (dist_dir / "index.html").write_text("<html></html>")
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        call_kwargs = mock_create_app.call_args.kwargs
        assert call_kwargs["static_dir"].resolve() == dist_dir.resolve()

    @patch("story_video.cli.uvicorn_run")
    @patch(f"{_WEB_APP_MODULE}.create_app")
    def test_static_dir_none_when_build_missing(
        self, mock_create_app, mock_uvicorn, tmp_path, monkeypatch
    ):
        """When web/dist/index.html is missing, create_app gets static_dir=None."""
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        call_kwargs = mock_create_app.call_args.kwargs
        assert call_kwargs.get("static_dir") is None

    @patch("story_video.cli.uvicorn_run")
    @patch(f"{_WEB_APP_MODULE}.create_app")
    def test_static_dir_none_when_dist_exists_but_no_index(
        self, mock_create_app, mock_uvicorn, tmp_path, monkeypatch
    ):
        """web/dist/ exists but has no index.html — treated as no build."""
        dist_dir = tmp_path / "web" / "dist"
        dist_dir.mkdir(parents=True)
        # No index.html
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        call_kwargs = mock_create_app.call_args.kwargs
        assert call_kwargs.get("static_dir") is None

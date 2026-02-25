"""Tests for the 'serve' CLI command."""

from unittest.mock import patch

from typer.testing import CliRunner

from story_video.cli import app

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

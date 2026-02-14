"""Integration tests for the CLI entry point."""

import subprocess
import sys


class TestCLIEntryPoint:
    """Verify the CLI loads and responds to basic commands."""

    def test_python_m_story_video_shows_help(self):
        """python -m story_video --help exits cleanly with usage info."""
        result = subprocess.run(
            [sys.executable, "-m", "story_video", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "story_video" in result.stdout
        assert "Commands" in result.stdout

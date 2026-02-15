"""Tests for CLI helpers and entry point."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from story_video.cli import (
    _display_outcome,
    _find_most_recent_project,
    _generate_project_id,
    _read_text_input,
)
from story_video.models import PhaseStatus, PipelinePhase


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


class TestGenerateProjectId:
    """Tests for _generate_project_id — collision-safe project ID generation."""

    def test_basic_format(self, tmp_path: Path) -> None:
        """Returns mode-YYYY-MM-DD format for a clean directory."""
        result = _generate_project_id("adapt", tmp_path)
        today = date.today().isoformat()
        assert result == f"adapt-{today}"

    def test_collision_suffix(self, tmp_path: Path) -> None:
        """Appends -2, -3 when directory already exists."""
        today = date.today().isoformat()

        # Create the base directory to cause a collision
        (tmp_path / f"adapt-{today}").mkdir()
        result = _generate_project_id("adapt", tmp_path)
        assert result == f"adapt-{today}-2"

        # Create the -2 directory to cause another collision
        (tmp_path / f"adapt-{today}-2").mkdir()
        result = _generate_project_id("adapt", tmp_path)
        assert result == f"adapt-{today}-3"

    def test_output_dir_does_not_exist(self, tmp_path: Path) -> None:
        """Works correctly when output_dir does not exist yet."""
        nonexistent = tmp_path / "does_not_exist"
        result = _generate_project_id("original", nonexistent)
        today = date.today().isoformat()
        assert result == f"original-{today}"


class TestReadTextInput:
    """Tests for _read_text_input — file-or-inline text reader."""

    def test_reads_file_when_path_exists(self, tmp_path: Path) -> None:
        """When value is a path to an existing file, reads its content."""
        text_file = tmp_path / "story.txt"
        text_file.write_text("Once upon a time...", encoding="utf-8")
        result = _read_text_input(str(text_file))
        assert result == "Once upon a time..."

    def test_returns_string_when_not_a_path(self) -> None:
        """When value is plain text (not a file path), returns it as-is."""
        result = _read_text_input("This is inline text for a story.")
        assert result == "This is inline text for a story."

    def test_returns_string_when_path_does_not_exist(self) -> None:
        """When value looks like a path but file doesn't exist, returns as-is."""
        result = _read_text_input("/tmp/nonexistent_file_abc123.txt")
        assert result == "/tmp/nonexistent_file_abc123.txt"


class TestFindMostRecentProject:
    """Tests for _find_most_recent_project — find latest project by created_at."""

    def test_returns_most_recent(self, tmp_path: Path) -> None:
        """With two projects, returns the one with the later created_at."""
        # Older project
        older = tmp_path / "project-old"
        older.mkdir()
        (older / "project.json").write_text(
            json.dumps(
                {
                    "project_id": "project-old",
                    "mode": "adapt",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )

        # Newer project
        newer = tmp_path / "project-new"
        newer.mkdir()
        (newer / "project.json").write_text(
            json.dumps(
                {
                    "project_id": "project-new",
                    "mode": "adapt",
                    "created_at": "2026-02-15T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )

        result = _find_most_recent_project(tmp_path)
        assert result == newer

    def test_returns_none_when_empty(self, tmp_path: Path) -> None:
        """Returns None for an empty directory with no projects."""
        result = _find_most_recent_project(tmp_path)
        assert result is None

    def test_skips_non_project_dirs(self, tmp_path: Path) -> None:
        """Directories without project.json are silently ignored."""
        # A directory without project.json
        (tmp_path / "random-dir").mkdir()

        # A valid project
        valid = tmp_path / "valid-project"
        valid.mkdir()
        (valid / "project.json").write_text(
            json.dumps(
                {
                    "project_id": "valid-project",
                    "mode": "adapt",
                    "created_at": "2026-01-15T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )

        result = _find_most_recent_project(tmp_path)
        assert result == valid

    def test_skips_corrupted_json(self, tmp_path: Path) -> None:
        """Corrupted project.json files are silently skipped."""
        # Corrupted project
        corrupted = tmp_path / "corrupted-project"
        corrupted.mkdir()
        (corrupted / "project.json").write_text(
            "this is not valid json {{{",
            encoding="utf-8",
        )

        # Valid project
        valid = tmp_path / "valid-project"
        valid.mkdir()
        (valid / "project.json").write_text(
            json.dumps(
                {
                    "project_id": "valid-project",
                    "mode": "adapt",
                    "created_at": "2026-02-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )

        result = _find_most_recent_project(tmp_path)
        assert result == valid

    def test_returns_none_when_dir_does_not_exist(self, tmp_path: Path) -> None:
        """Returns None when the output directory itself doesn't exist."""
        nonexistent = tmp_path / "no_such_dir"
        result = _find_most_recent_project(nonexistent)
        assert result is None


class TestDisplayOutcome:
    """Tests for _display_outcome — Rich panel display based on project status."""

    def test_completed_shows_success(self, capsys) -> None:
        """COMPLETED status prints a success-related message."""
        state = MagicMock()
        state.metadata.status = PhaseStatus.COMPLETED
        state.project_dir = Path("/output/my-project")

        _display_outcome(state)

        captured = capsys.readouterr().out.lower()
        assert "success" in captured or "complete" in captured

    def test_awaiting_review_shows_paused(self, capsys) -> None:
        """AWAITING_REVIEW status prints a paused/review message."""
        state = MagicMock()
        state.metadata.status = PhaseStatus.AWAITING_REVIEW
        state.metadata.current_phase = PipelinePhase.SCENE_SPLITTING

        _display_outcome(state)

        captured = capsys.readouterr().out.lower()
        assert "review" in captured or "paused" in captured

    def test_failed_shows_error(self, capsys) -> None:
        """FAILED status prints a failure/error message."""
        state = MagicMock()
        state.metadata.status = PhaseStatus.FAILED
        state.metadata.current_phase = PipelinePhase.TTS_GENERATION

        _display_outcome(state)

        captured = capsys.readouterr().out.lower()
        assert "failed" in captured or "error" in captured

"""Tests for CLI helpers and entry point."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from story_video.cli import (
    _display_outcome,
    _find_most_recent_project,
    _generate_project_id,
    _read_text_input,
    app,
)
from story_video.models import PhaseStatus, PipelinePhase

runner = CliRunner()


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


class TestCreateCommand:
    """Tests for the create CLI command — validate, configure, run pipeline."""

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_create_adapt_happy_path(
        self, mock_claude, mock_tts, mock_image, mock_whisper, mock_run, tmp_path
    ):
        """Creates project, writes source_story.txt, calls run_pipeline."""
        source_file = tmp_path / "story.txt"
        source_file.write_text("Once upon a time...", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "create",
                "--mode",
                "adapt",
                "--source-material",
                str(source_file),
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert result.exit_code == 0
        mock_run.assert_called_once()
        call_state = mock_run.call_args[0][0]
        assert (call_state.project_dir / "source_story.txt").read_text(
            encoding="utf-8"
        ) == "Once upon a time..."

    def test_create_adapt_missing_source_material(self, tmp_path):
        """Adapt without --source-material -> error."""
        result = runner.invoke(
            app,
            [
                "create",
                "--mode",
                "adapt",
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert result.exit_code != 0
        assert "source-material" in result.output.lower()

    def test_create_original_mode_not_implemented(self, tmp_path):
        """Original mode -> 'not yet implemented'."""
        result = runner.invoke(
            app,
            [
                "create",
                "--mode",
                "original",
                "--topic",
                "A lighthouse",
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert result.exit_code != 0
        assert "not yet implemented" in result.output.lower()

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_create_config_overrides(
        self, mock_claude, mock_tts, mock_image, mock_whisper, mock_run, tmp_path
    ):
        """--voice, --duration, --autonomous flow to config."""
        source_file = tmp_path / "story.txt"
        source_file.write_text("Story.", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "create",
                "--mode",
                "adapt",
                "--source-material",
                str(source_file),
                "--output-dir",
                str(tmp_path / "output"),
                "--voice",
                "alloy",
                "--duration",
                "45",
                "--autonomous",
            ],
        )
        assert result.exit_code == 0
        call_state = mock_run.call_args[0][0]
        assert call_state.metadata.config.tts.voice == "alloy"
        assert call_state.metadata.config.story.target_duration_minutes == 45
        assert call_state.metadata.config.pipeline.autonomous is True

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_create_reads_inline_source(
        self, mock_claude, mock_tts, mock_image, mock_whisper, mock_run, tmp_path
    ):
        """Inline text (not file) used as source."""
        result = runner.invoke(
            app,
            [
                "create",
                "--mode",
                "adapt",
                "--source-material",
                "Once upon a time in a land far away...",
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert result.exit_code == 0
        call_state = mock_run.call_args[0][0]
        assert (call_state.project_dir / "source_story.txt").read_text(
            encoding="utf-8"
        ) == "Once upon a time in a land far away..."

    @patch("story_video.cli.run_pipeline", side_effect=RuntimeError("API failed"))
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_create_pipeline_error_shown(
        self, mock_claude, mock_tts, mock_image, mock_whisper, mock_run, tmp_path
    ):
        """Pipeline error -> error panel, non-zero exit."""
        source_file = tmp_path / "story.txt"
        source_file.write_text("Story.", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "create",
                "--mode",
                "adapt",
                "--source-material",
                str(source_file),
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert result.exit_code != 0
        assert "api failed" in result.output.lower()

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_create_providers_passed_to_pipeline(
        self, mock_claude, mock_tts, mock_image, mock_whisper, mock_run, tmp_path
    ):
        """All 4 providers passed to run_pipeline."""
        source_file = tmp_path / "story.txt"
        source_file.write_text("Text.", encoding="utf-8")
        runner.invoke(
            app,
            [
                "create",
                "--mode",
                "adapt",
                "--source-material",
                str(source_file),
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["claude_client"] == mock_claude.return_value
        assert call_kwargs["tts_provider"] == mock_tts.return_value
        assert call_kwargs["image_provider"] == mock_image.return_value
        assert call_kwargs["caption_provider"] == mock_whisper.return_value


class TestResumeCommand:
    """Tests for the resume CLI command — load existing project and continue pipeline."""

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_resume_with_project_id(
        self, mock_claude, mock_tts, mock_image, mock_whisper, mock_run, tmp_path
    ):
        """Loads specified project and calls run_pipeline."""
        from story_video.models import AppConfig, InputMode
        from story_video.state import ProjectState

        ProjectState.create(
            project_id="test-project",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        result = runner.invoke(app, ["resume", "test-project", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_resume_without_id_uses_most_recent(
        self, mock_claude, mock_tts, mock_image, mock_whisper, mock_run, tmp_path
    ):
        """No project ID → resumes most recent project."""
        from story_video.models import AppConfig, InputMode
        from story_video.state import ProjectState

        ProjectState.create(
            project_id="my-latest",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        result = runner.invoke(app, ["resume", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        mock_run.assert_called_once()
        loaded_state = mock_run.call_args[0][0]
        assert loaded_state.metadata.project_id == "my-latest"

    def test_resume_no_projects_found(self, tmp_path):
        """Empty output dir → error."""
        result = runner.invoke(app, ["resume", "--output-dir", str(tmp_path)])
        assert result.exit_code != 0
        assert "no project" in result.output.lower()

    def test_resume_invalid_project_id(self, tmp_path):
        """Non-existent project ID → error."""
        result = runner.invoke(
            app, ["resume", "nonexistent-project", "--output-dir", str(tmp_path)]
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestEstimateCommand:
    """Tests for the estimate CLI command — projected cost display."""

    def test_estimate_adapt(self):
        """Adapt mode estimate displays cost breakdown."""
        result = runner.invoke(app, ["estimate", "--mode", "adapt"])
        assert result.exit_code == 0
        assert "cost estimate" in result.output.lower()
        assert "claude" in result.output.lower()
        assert "$" in result.output

    def test_estimate_original(self):
        """Original mode works for estimate (all modes supported)."""
        result = runner.invoke(app, ["estimate", "--mode", "original"])
        assert result.exit_code == 0
        assert "cost estimate" in result.output.lower()

    def test_estimate_inspired_by(self):
        """Inspired_by mode works for estimate."""
        result = runner.invoke(app, ["estimate", "--mode", "inspired_by"])
        assert result.exit_code == 0
        assert "cost estimate" in result.output.lower()

    def test_estimate_with_duration_override(self):
        """--duration affects the estimate."""
        result = runner.invoke(app, ["estimate", "--mode", "adapt", "--duration", "60"])
        assert result.exit_code == 0
        assert "60 minutes" in result.output

    def test_estimate_with_voice_override(self):
        """--voice affects the estimate (changes TTS model cost)."""
        result = runner.invoke(app, ["estimate", "--mode", "adapt", "--voice", "nova"])
        assert result.exit_code == 0
        assert "cost estimate" in result.output.lower()

    def test_estimate_invalid_mode(self):
        """Unknown mode shows an error."""
        result = runner.invoke(app, ["estimate", "--mode", "nonexistent"])
        assert result.exit_code != 0
        assert "unknown mode" in result.output.lower()

    def test_estimate_does_not_create_project(self):
        """Estimate doesn't call ProjectState.create."""
        with patch("story_video.cli.ProjectState") as mock_state:
            result = runner.invoke(app, ["estimate", "--mode", "adapt"])
            assert result.exit_code == 0
            mock_state.create.assert_not_called()


class TestStatusCommand:
    """Tests for the status CLI command — project state display."""

    def test_status_with_project_id(self, tmp_path):
        """Displays project metadata and scene status."""
        from story_video.models import AppConfig, AssetType, InputMode, SceneStatus
        from story_video.state import ProjectState

        state = ProjectState.create(
            project_id="status-test",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        state.add_scene(1, "Opening", "The story begins.")
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.IN_PROGRESS)
        state.update_scene_asset(1, AssetType.TEXT, SceneStatus.COMPLETED)
        state.save()

        result = runner.invoke(app, ["status", "status-test", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "status-test" in result.output
        assert "adapt" in result.output.lower()

    def test_status_no_id_uses_most_recent(self, tmp_path):
        """No project ID → shows most recent."""
        from story_video.models import AppConfig, InputMode
        from story_video.state import ProjectState

        ProjectState.create(
            project_id="latest-project",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )

        result = runner.invoke(app, ["status", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "latest-project" in result.output

    def test_status_no_projects(self, tmp_path):
        """Empty output dir → error."""
        result = runner.invoke(app, ["status", "--output-dir", str(tmp_path)])
        assert result.exit_code != 0
        assert "no project" in result.output.lower()


class TestListCommand:
    """Tests for the list CLI command — project listing display."""

    def test_list_shows_projects(self, tmp_path):
        """Lists all projects with metadata."""
        from story_video.models import AppConfig, InputMode
        from story_video.state import ProjectState

        ProjectState.create(
            project_id="project-a",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        ProjectState.create(
            project_id="project-b",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )

        result = runner.invoke(app, ["list", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "project-a" in result.output
        assert "project-b" in result.output

    def test_list_empty(self, tmp_path):
        """No projects → clean message."""
        result = runner.invoke(app, ["list", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "no project" in result.output.lower()

    def test_list_skips_corrupted(self, tmp_path):
        """Corrupted project.json skipped."""
        from story_video.models import AppConfig, InputMode
        from story_video.state import ProjectState

        ProjectState.create(
            project_id="good-project",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        bad = tmp_path / "bad-project"
        bad.mkdir()
        (bad / "project.json").write_text("{broken", encoding="utf-8")

        result = runner.invoke(app, ["list", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "good-project" in result.output


class TestProviderSelection:
    """CLI selects TTS provider based on tts.provider config."""

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.ElevenLabsTTSProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_default_openai_provider(
        self,
        mock_claude,
        mock_openai_tts,
        mock_eleven_tts,
        mock_image,
        mock_whisper,
        mock_run,
        tmp_path,
    ):
        """Default config creates OpenAITTSProvider."""
        source_file = tmp_path / "story.txt"
        source_file.write_text("Story text.", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "create",
                "--mode",
                "adapt",
                "--source-material",
                str(source_file),
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert result.exit_code == 0
        mock_openai_tts.assert_called_once()
        mock_eleven_tts.assert_not_called()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["tts_provider"] == mock_openai_tts.return_value

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.ElevenLabsTTSProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_elevenlabs_provider_when_configured(
        self,
        mock_claude,
        mock_openai_tts,
        mock_eleven_tts,
        mock_image,
        mock_whisper,
        mock_run,
        tmp_path,
    ):
        """provider='elevenlabs' in config creates ElevenLabsTTSProvider."""
        # Write a config file that sets tts.provider to elevenlabs
        config_file = tmp_path / "config.yaml"
        config_file.write_text("tts:\n  provider: elevenlabs\n", encoding="utf-8")

        source_file = tmp_path / "story.txt"
        source_file.write_text("Story text.", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "create",
                "--mode",
                "adapt",
                "--source-material",
                str(source_file),
                "--output-dir",
                str(tmp_path / "output"),
                "--config",
                str(config_file),
            ],
        )
        assert result.exit_code == 0
        mock_eleven_tts.assert_called_once()
        mock_openai_tts.assert_not_called()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["tts_provider"] == mock_eleven_tts.return_value

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.ElevenLabsTTSProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_resume_elevenlabs_provider_when_configured(
        self,
        mock_claude,
        mock_openai_tts,
        mock_eleven_tts,
        mock_image,
        mock_whisper,
        mock_run,
        tmp_path,
    ):
        """Resume with provider='elevenlabs' in stored config creates ElevenLabsTTSProvider."""
        from story_video.models import AppConfig, InputMode, TTSConfig
        from story_video.state import ProjectState

        config = AppConfig(tts=TTSConfig(provider="elevenlabs"))
        ProjectState.create(
            project_id="eleven-project",
            mode=InputMode.ADAPT,
            config=config,
            output_dir=tmp_path,
        )

        result = runner.invoke(app, ["resume", "eleven-project", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        mock_eleven_tts.assert_called_once()
        mock_openai_tts.assert_not_called()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["tts_provider"] == mock_eleven_tts.return_value

    def test_unknown_provider_exits_with_error(self, tmp_path, monkeypatch):
        """Unknown provider string produces an error, not silent OpenAI fallback."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("tts:\n  provider: google\n", encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "create",
                "--mode",
                "adapt",
                "--source-material",
                "Test story text.",
                "--config",
                str(config_path),
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert result.exit_code == 1
        assert "unknown" in result.output.lower() or "unsupported" in result.output.lower()


class TestRunWithProviders:
    """_run_with_providers instantiates providers and calls run_pipeline."""

    def test_calls_run_pipeline_with_all_providers(self, monkeypatch):
        """Helper instantiates all 4 providers and passes them to run_pipeline."""
        mock_run = MagicMock()
        monkeypatch.setattr("story_video.cli.run_pipeline", mock_run)
        monkeypatch.setattr("story_video.cli.ClaudeClient", MagicMock)
        monkeypatch.setattr("story_video.cli.OpenAIImageProvider", MagicMock)
        monkeypatch.setattr("story_video.cli.OpenAIWhisperProvider", MagicMock)
        monkeypatch.setattr("story_video.cli._make_tts_provider", MagicMock())

        state = MagicMock()
        state.metadata.config.tts.provider = "openai"

        from story_video.cli import _run_with_providers

        _run_with_providers(state)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert "claude_client" in call_kwargs
        assert "tts_provider" in call_kwargs
        assert "image_provider" in call_kwargs
        assert "caption_provider" in call_kwargs


class TestDisplayOutcomeSuccessPath:
    """_display_outcome success message points to final.mp4."""

    def test_success_message_contains_final_mp4(self, tmp_path, capsys):
        """Success panel mentions 'final.mp4' not 'video' directory."""
        from story_video.models import AppConfig, InputMode, PhaseStatus
        from story_video.state import ProjectState

        state = ProjectState.create("test-proj", InputMode.ADAPT, AppConfig(), tmp_path)
        state.metadata.status = PhaseStatus.COMPLETED
        state.save()

        _display_outcome(state)

        captured = capsys.readouterr().out
        assert "final.mp4" in captured
        assert "video" not in captured.lower() or "video is at" in captured.lower()

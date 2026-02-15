# CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the 5 CLI commands (create, resume, estimate, status, list) as a thin wiring layer over existing modules.

**Architecture:** The CLI parses user input via Typer, loads config, creates/loads state, instantiates providers inline, and delegates to the orchestrator or cost module. Rich provides formatted terminal output. Only adapt mode is supported for create/resume; estimate supports all modes.

**Tech Stack:** Typer (CLI framework), Rich (terminal formatting), existing modules (config, state, cost, orchestrator, providers)

**Status:** Complete

---

## Context for the Implementer

### Key files you will modify or create

| File | Action |
|------|--------|
| `src/story_video/cli.py` | Rewrite — replace stubs with full implementations |
| `tests/test_cli.py` | Rewrite — replace single test with comprehensive suite |

### Key files you must read and understand

| File | Why |
|------|-----|
| `src/story_video/config.py` | `load_config(config_path, cli_overrides)` — three-way merge |
| `src/story_video/state.py` | `ProjectState.create()`, `ProjectState.load()`, `.save()` |
| `src/story_video/cost.py` | `estimate_cost()`, `format_cost_estimate()` |
| `src/story_video/pipeline/orchestrator.py` | `run_pipeline(state, claude_client=, tts_provider=, image_provider=, caption_provider=)` |
| `src/story_video/pipeline/claude_client.py` | `ClaudeClient()` constructor |
| `src/story_video/pipeline/tts_generator.py` | `OpenAITTSProvider()` constructor |
| `src/story_video/pipeline/image_generator.py` | `OpenAIImageProvider()` constructor |
| `src/story_video/pipeline/caption_generator.py` | `OpenAIWhisperProvider()` constructor |
| `src/story_video/models.py` | `InputMode`, `PhaseStatus`, `AppConfig`, `ProjectMetadata`, `Scene`, `AssetType` |

### How source text flows through the system

For adapt mode, `split_scenes()` reads `source_story.txt` from the project directory:
```python
source_path = state.project_dir / "source_story.txt"  # story_writer.py:144
```

So the `create` command must:
1. Create the project state (creates directory structure)
2. Write source material to `project_dir / "source_story.txt"`
3. Then call `run_pipeline()`

### Config overrides mapping

CLI flags map to dotted config keys for `load_config(cli_overrides=...)`:
- `--voice nova` → `{"tts.voice": "nova"}`
- `--duration 30` → `{"story.target_duration_minutes": 30}`
- `--autonomous` → `{"pipeline.autonomous": True}`

### Provider imports

```python
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.tts_generator import OpenAITTSProvider
from story_video.pipeline.image_generator import OpenAIImageProvider
from story_video.pipeline.caption_generator import OpenAIWhisperProvider
```

### Rich is already a dependency

`pyproject.toml` already includes `rich>=13.0` and `typer[all]>=0.12.0`. No dependency changes needed.

---

## Task 1: CLI Helpers

**Files:**
- Modify: `src/story_video/cli.py`
- Modify: `tests/test_cli.py`

Implement 4 helper functions that all commands will use: project ID generation, text input reading, most-recent-project lookup, and pipeline outcome display. These are pure functions (except display) that can be thoroughly tested without mocking the orchestrator.

### Tests to write

```python
"""Tests for CLI helper functions."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from story_video.cli import (
    _display_outcome,
    _find_most_recent_project,
    _generate_project_id,
    _read_text_input,
)
from story_video.models import PhaseStatus, PipelinePhase


runner = CliRunner()


# ---------------------------------------------------------------------------
# _generate_project_id
# ---------------------------------------------------------------------------


class TestGenerateProjectId:
    """Project ID generation with collision avoidance."""

    def test_basic_format(self, tmp_path):
        """Returns mode-YYYY-MM-DD format."""
        result = _generate_project_id("adapt", tmp_path)
        assert result.startswith("adapt-")
        # Verify date portion is valid (YYYY-MM-DD)
        date_part = result.removeprefix("adapt-")
        datetime.strptime(date_part, "%Y-%m-%d")

    def test_collision_suffix(self, tmp_path):
        """Appends -2, -3 on collision."""
        # Create first project dir to cause collision
        first_id = _generate_project_id("adapt", tmp_path)
        (tmp_path / first_id).mkdir()

        second_id = _generate_project_id("adapt", tmp_path)
        assert second_id == f"{first_id}-2"

        (tmp_path / second_id).mkdir()
        third_id = _generate_project_id("adapt", tmp_path)
        assert third_id == f"{first_id}-3"

    def test_output_dir_does_not_exist(self, tmp_path):
        """Works even if output_dir doesn't exist yet."""
        nonexistent = tmp_path / "not_here"
        result = _generate_project_id("adapt", nonexistent)
        assert result.startswith("adapt-")


# ---------------------------------------------------------------------------
# _read_text_input
# ---------------------------------------------------------------------------


class TestReadTextInput:
    """Read text from file path or inline string."""

    def test_reads_file_when_path_exists(self, tmp_path):
        """If value is a path to existing file, reads file content."""
        f = tmp_path / "story.txt"
        f.write_text("Once upon a time...", encoding="utf-8")
        result = _read_text_input(str(f))
        assert result == "Once upon a time..."

    def test_returns_string_when_not_a_path(self):
        """If value is not a file path, returns as-is."""
        result = _read_text_input("A lighthouse keeper discovers a portal")
        assert result == "A lighthouse keeper discovers a portal"

    def test_returns_string_when_path_does_not_exist(self):
        """Non-existent path is treated as inline text."""
        result = _read_text_input("/no/such/file.txt")
        assert result == "/no/such/file.txt"


# ---------------------------------------------------------------------------
# _find_most_recent_project
# ---------------------------------------------------------------------------


class TestFindMostRecentProject:
    """Find most recent project in output directory."""

    def test_returns_most_recent(self, tmp_path):
        """Returns project with latest created_at."""
        # Older project
        older = tmp_path / "project-old"
        older.mkdir()
        (older / "project.json").write_text(
            json.dumps({"project_id": "old", "mode": "adapt",
                        "created_at": "2026-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        # Newer project
        newer = tmp_path / "project-new"
        newer.mkdir()
        (newer / "project.json").write_text(
            json.dumps({"project_id": "new", "mode": "adapt",
                        "created_at": "2026-02-15T00:00:00Z"}),
            encoding="utf-8",
        )

        result = _find_most_recent_project(tmp_path)
        assert result == newer

    def test_returns_none_when_empty(self, tmp_path):
        """Empty output dir returns None."""
        assert _find_most_recent_project(tmp_path) is None

    def test_skips_non_project_dirs(self, tmp_path):
        """Directories without project.json are ignored."""
        (tmp_path / "random_dir").mkdir()
        (tmp_path / "some_file.txt").write_text("hi", encoding="utf-8")
        assert _find_most_recent_project(tmp_path) is None

    def test_skips_corrupted_json(self, tmp_path):
        """Corrupted project.json files are silently skipped."""
        bad = tmp_path / "bad-project"
        bad.mkdir()
        (bad / "project.json").write_text("{invalid", encoding="utf-8")

        good = tmp_path / "good-project"
        good.mkdir()
        (good / "project.json").write_text(
            json.dumps({"project_id": "good", "mode": "adapt",
                        "created_at": "2026-02-15T00:00:00Z"}),
            encoding="utf-8",
        )

        result = _find_most_recent_project(tmp_path)
        assert result == good

    def test_returns_none_when_dir_does_not_exist(self, tmp_path):
        """Non-existent output dir returns None."""
        result = _find_most_recent_project(tmp_path / "nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# _display_outcome
# ---------------------------------------------------------------------------


class TestDisplayOutcome:
    """Pipeline outcome display via Rich."""

    def test_completed_shows_success(self, capsys):
        """COMPLETED status shows success panel."""
        state = MagicMock()
        state.metadata.status = PhaseStatus.COMPLETED
        state.project_dir = Path("/output/my-project")

        _display_outcome(state)

        captured = capsys.readouterr()
        assert "complete" in captured.out.lower() or "success" in captured.out.lower()

    def test_awaiting_review_shows_paused(self, capsys):
        """AWAITING_REVIEW status shows paused info."""
        state = MagicMock()
        state.metadata.status = PhaseStatus.AWAITING_REVIEW
        state.metadata.current_phase = PipelinePhase.SCENE_SPLITTING

        _display_outcome(state)

        captured = capsys.readouterr()
        assert "review" in captured.out.lower() or "paused" in captured.out.lower()

    def test_failed_shows_error(self, capsys):
        """FAILED status shows error info."""
        state = MagicMock()
        state.metadata.status = PhaseStatus.FAILED
        state.metadata.current_phase = PipelinePhase.TTS_GENERATION

        _display_outcome(state)

        captured = capsys.readouterr()
        assert "failed" in captured.out.lower() or "error" in captured.out.lower()
```

### Implementation

```python
"""CLI helper functions for project management and display."""

import json
import logging
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from story_video.models import PhaseStatus
from story_video.state import ProjectState

logger = logging.getLogger(__name__)
console = Console()


def _generate_project_id(mode: str, output_dir: Path) -> str:
    """Generate a collision-safe project ID.

    Format: {mode}-{YYYY-MM-DD}, with -2, -3 suffix on collision.

    Args:
        mode: Input mode name (e.g., "adapt").
        output_dir: Base output directory to check for collisions.

    Returns:
        A unique project ID string.
    """
    base = f"{mode}-{date.today().isoformat()}"
    candidate = base

    if not output_dir.exists():
        return candidate

    suffix = 2
    while (output_dir / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1

    return candidate


def _read_text_input(value: str) -> str:
    """Read text from a file path or return inline string.

    If value is a path to an existing file, reads and returns its content.
    Otherwise returns the value as-is (inline text).

    Args:
        value: File path or inline text string.

    Returns:
        The text content.
    """
    path = Path(value)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return value


def _find_most_recent_project(output_dir: Path) -> Path | None:
    """Find the most recently created project in the output directory.

    Scans for subdirectories containing project.json, reads the created_at
    field (lightweight JSON parse), and returns the most recent.

    Args:
        output_dir: Base output directory containing project subdirectories.

    Returns:
        Path to the most recent project directory, or None if no projects exist.
    """
    if not output_dir.exists():
        return None

    candidates: list[tuple[str, Path]] = []
    for child in output_dir.iterdir():
        if not child.is_dir():
            continue
        json_path = child / "project.json"
        if not json_path.exists():
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            created_at = data.get("created_at", "")
            candidates.append((created_at, child))
        except (json.JSONDecodeError, OSError):
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _display_outcome(state: ProjectState) -> None:
    """Display pipeline outcome using Rich panels.

    Shows a colored panel based on the pipeline's final status:
    - COMPLETED: green success panel with video path
    - AWAITING_REVIEW: yellow info panel with resume instructions
    - FAILED: red error panel with phase info

    Args:
        state: Project state to inspect for outcome.
    """
    status = state.metadata.status
    phase = state.metadata.current_phase

    if status == PhaseStatus.COMPLETED:
        video_dir = state.project_dir / "video"
        console.print(Panel(
            f"Pipeline complete! Output at {video_dir}",
            title="Success",
            style="green",
        ))
    elif status == PhaseStatus.AWAITING_REVIEW:
        phase_name = phase.value if phase else "unknown"
        console.print(Panel(
            f"Paused at [bold]{phase_name}[/bold] for review.\n"
            f"Run [bold]story-video resume[/bold] to continue.",
            title="Paused for Review",
            style="yellow",
        ))
    elif status == PhaseStatus.FAILED:
        phase_name = phase.value if phase else "unknown"
        console.print(Panel(
            f"Failed at [bold]{phase_name}[/bold].\n"
            f"Run [bold]story-video resume[/bold] to retry.",
            title="Error",
            style="red",
        ))
```

**Run:** `pytest tests/test_cli.py -v`
Expected: All helper tests pass.

**Commit:** `git add src/story_video/cli.py tests/test_cli.py && git commit -m "feat(cli): add helper functions — project ID, text input, recent project, outcome display"`

---

## Task 2: `create` Command

**Files:**
- Modify: `src/story_video/cli.py`
- Modify: `tests/test_cli.py`

The `create` command validates mode-specific requirements, builds config with CLI overrides, creates project state, writes source material to disk, instantiates providers, and runs the pipeline.

### Key behaviors

1. **Mode validation:** Only `adapt` is supported for `create` (creative flow not implemented). Other modes get a clear error.
2. **Source material validation:** `adapt` requires `--source-material`. Must be provided.
3. **Config override mapping:** `--voice` → `tts.voice`, `--duration` → `story.target_duration_minutes`, `--autonomous` → `pipeline.autonomous`.
4. **Source text storage:** Written to `project_dir / "source_story.txt"` (read by `split_scenes`).
5. **Provider instantiation:** Inline — `ClaudeClient()`, `OpenAITTSProvider()`, etc.
6. **Outcome display:** Uses `_display_outcome()` after `run_pipeline()` returns.
7. **Error handling:** Catches pipeline exceptions, displays Rich error panel.

### Tests to write

```python
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from story_video.cli import app
from story_video.models import InputMode, PhaseStatus


runner = CliRunner()


class TestCreateCommand:
    """story-video create — start a new project."""

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_create_adapt_happy_path(
        self, mock_claude, mock_tts, mock_image, mock_whisper,
        mock_run, tmp_path
    ):
        """Adapt mode: creates project, writes source, calls run_pipeline."""
        source_file = tmp_path / "story.txt"
        source_file.write_text("Once upon a time...", encoding="utf-8")

        result = runner.invoke(app, [
            "create",
            "--mode", "adapt",
            "--source-material", str(source_file),
            "--output-dir", str(tmp_path / "output"),
        ])

        assert result.exit_code == 0
        # run_pipeline was called
        mock_run.assert_called_once()
        # Source text was written to project dir
        call_state = mock_run.call_args[0][0]  # first positional arg
        source_story = call_state.project_dir / "source_story.txt"
        assert source_story.read_text(encoding="utf-8") == "Once upon a time..."

    def test_create_adapt_missing_source_material(self, tmp_path):
        """Adapt mode without --source-material fails with clear error."""
        result = runner.invoke(app, [
            "create",
            "--mode", "adapt",
            "--output-dir", str(tmp_path / "output"),
        ])
        assert result.exit_code != 0
        assert "source-material" in result.output.lower()

    def test_create_original_mode_not_implemented(self, tmp_path):
        """Original mode rejected with 'not yet implemented' message."""
        result = runner.invoke(app, [
            "create",
            "--mode", "original",
            "--topic", "A lighthouse keeper",
            "--output-dir", str(tmp_path / "output"),
        ])
        assert result.exit_code != 0
        assert "not yet implemented" in result.output.lower()

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_create_config_overrides(
        self, mock_claude, mock_tts, mock_image, mock_whisper,
        mock_run, tmp_path
    ):
        """CLI flags flow through to config as overrides."""
        source_file = tmp_path / "story.txt"
        source_file.write_text("Story text here.", encoding="utf-8")

        result = runner.invoke(app, [
            "create",
            "--mode", "adapt",
            "--source-material", str(source_file),
            "--output-dir", str(tmp_path / "output"),
            "--voice", "alloy",
            "--duration", "45",
            "--autonomous",
        ])

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
        self, mock_claude, mock_tts, mock_image, mock_whisper,
        mock_run, tmp_path
    ):
        """Inline text (not a file path) used directly as source material."""
        result = runner.invoke(app, [
            "create",
            "--mode", "adapt",
            "--source-material", "Once upon a time in a land far away...",
            "--output-dir", str(tmp_path / "output"),
        ])

        assert result.exit_code == 0
        call_state = mock_run.call_args[0][0]
        source_story = call_state.project_dir / "source_story.txt"
        assert source_story.read_text(encoding="utf-8") == "Once upon a time in a land far away..."

    @patch("story_video.cli.run_pipeline", side_effect=RuntimeError("API failed"))
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_create_pipeline_error_shown(
        self, mock_claude, mock_tts, mock_image, mock_whisper,
        mock_run, tmp_path
    ):
        """Pipeline exception displayed as error, non-zero exit."""
        source_file = tmp_path / "story.txt"
        source_file.write_text("Story text.", encoding="utf-8")

        result = runner.invoke(app, [
            "create",
            "--mode", "adapt",
            "--source-material", str(source_file),
            "--output-dir", str(tmp_path / "output"),
        ])

        assert result.exit_code != 0
        assert "api failed" in result.output.lower()

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_create_providers_passed_to_pipeline(
        self, mock_claude, mock_tts, mock_image, mock_whisper,
        mock_run, tmp_path
    ):
        """All 4 providers instantiated and passed to run_pipeline."""
        source_file = tmp_path / "story.txt"
        source_file.write_text("Text.", encoding="utf-8")

        runner.invoke(app, [
            "create",
            "--mode", "adapt",
            "--source-material", str(source_file),
            "--output-dir", str(tmp_path / "output"),
        ])

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["claude_client"] == mock_claude.return_value
        assert call_kwargs["tts_provider"] == mock_tts.return_value
        assert call_kwargs["image_provider"] == mock_image.return_value
        assert call_kwargs["caption_provider"] == mock_whisper.return_value
```

### Implementation

```python
@app.command()
def create(
    mode: str = typer.Option(..., help="Input mode: adapt (original/inspired_by coming soon)"),
    source_material: str | None = typer.Option(None, help="Source story text or path to file"),
    topic: str | None = typer.Option(None, help="Story topic/premise (for original mode)"),
    style_reference: Path | None = typer.Option(None, exists=True, help="Path to style sample"),
    duration: int | None = typer.Option(None, help="Target duration in minutes"),
    voice: str | None = typer.Option(None, help="TTS voice name"),
    autonomous: bool = typer.Option(False, help="Skip human review checkpoints"),
    output_dir: Path = typer.Option(Path("./output"), help="Output directory"),
    config: Path | None = typer.Option(None, help="Path to config.yaml"),
) -> None:
    """Start a new story video project."""
    # Validate mode
    try:
        input_mode = InputMode(mode)
    except ValueError:
        console.print(f"[red]Unknown mode: {mode}. Choose from: adapt, original, inspired_by[/red]")
        raise typer.Exit(1)

    if input_mode != InputMode.ADAPT:
        console.print(f"[red]Mode '{mode}' is not yet implemented. Only 'adapt' is supported.[/red]")
        raise typer.Exit(1)

    # Validate mode-specific requirements
    if input_mode == InputMode.ADAPT and not source_material:
        console.print("[red]--source-material is required for adapt mode.[/red]")
        raise typer.Exit(1)

    # Build config with CLI overrides
    cli_overrides: dict[str, Any] = {}
    if duration is not None:
        cli_overrides["story.target_duration_minutes"] = duration
    if voice is not None:
        cli_overrides["tts.voice"] = voice
    if autonomous:
        cli_overrides["pipeline.autonomous"] = True

    app_config = load_config(
        config_path=config,
        cli_overrides=cli_overrides if cli_overrides else None,
    )

    # Create project
    project_id = _generate_project_id(mode, output_dir)
    state = ProjectState.create(
        project_id=project_id,
        mode=input_mode,
        config=app_config,
        output_dir=output_dir,
    )

    # Write source material to project directory
    if source_material:
        source_text = _read_text_input(source_material)
        (state.project_dir / "source_story.txt").write_text(source_text, encoding="utf-8")

    console.print(f"Created project [bold]{project_id}[/bold] at {state.project_dir}")

    # Instantiate providers and run pipeline
    try:
        claude_client = ClaudeClient()
        tts_provider = OpenAITTSProvider()
        image_provider = OpenAIImageProvider()
        caption_provider = OpenAIWhisperProvider()

        run_pipeline(
            state,
            claude_client=claude_client,
            tts_provider=tts_provider,
            image_provider=image_provider,
            caption_provider=caption_provider,
        )
        _display_outcome(state)
    except Exception as exc:
        console.print(Panel(str(exc), title="Error", style="red"))
        raise typer.Exit(1)
```

**Run:** `pytest tests/test_cli.py -v`
Expected: All create tests pass.

**Commit:** `git add src/story_video/cli.py tests/test_cli.py && git commit -m "feat(cli): implement create command — validate, configure, run pipeline"`

---

## Task 3: `resume` Command

**Files:**
- Modify: `src/story_video/cli.py`
- Modify: `tests/test_cli.py`

The `resume` command loads an existing project (by ID or most-recent), instantiates providers, and calls `run_pipeline()`. The orchestrator's resume logic handles the rest.

### Tests to write

```python
class TestResumeCommand:
    """story-video resume — continue a paused/failed project."""

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_resume_with_project_id(
        self, mock_claude, mock_tts, mock_image, mock_whisper,
        mock_run, tmp_path
    ):
        """Loads specified project and calls run_pipeline."""
        # Create a real project to resume
        state = ProjectState.create(
            project_id="test-project",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )

        result = runner.invoke(app, [
            "resume",
            "test-project",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("story_video.cli.run_pipeline")
    @patch("story_video.cli.OpenAIWhisperProvider")
    @patch("story_video.cli.OpenAIImageProvider")
    @patch("story_video.cli.OpenAITTSProvider")
    @patch("story_video.cli.ClaudeClient")
    def test_resume_without_id_uses_most_recent(
        self, mock_claude, mock_tts, mock_image, mock_whisper,
        mock_run, tmp_path
    ):
        """No project ID → resumes most recent project."""
        state = ProjectState.create(
            project_id="my-latest",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )

        result = runner.invoke(app, [
            "resume",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        loaded_state = mock_run.call_args[0][0]
        assert loaded_state.metadata.project_id == "my-latest"

    def test_resume_no_projects_found(self, tmp_path):
        """Empty output dir → error message."""
        result = runner.invoke(app, [
            "resume",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "no project" in result.output.lower()

    def test_resume_invalid_project_id(self, tmp_path):
        """Non-existent project ID → error message."""
        result = runner.invoke(app, [
            "resume",
            "nonexistent-project",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()
```

### Implementation

```python
@app.command()
def resume(
    project_id: str | None = typer.Argument(None, help="Project ID to resume (default: most recent)"),
    output_dir: Path = typer.Option(Path("./output"), help="Output directory"),
) -> None:
    """Resume a paused or failed project."""
    # Find project directory
    if project_id:
        project_dir = output_dir / project_id
        if not (project_dir / "project.json").exists():
            console.print(f"[red]Project '{project_id}' not found in {output_dir}[/red]")
            raise typer.Exit(1)
    else:
        project_dir = _find_most_recent_project(output_dir)
        if project_dir is None:
            console.print(f"[red]No projects found in {output_dir}[/red]")
            raise typer.Exit(1)

    # Load project state
    try:
        state = ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as exc:
        console.print(Panel(str(exc), title="Error", style="red"))
        raise typer.Exit(1)

    console.print(f"Resuming project [bold]{state.metadata.project_id}[/bold]")

    # Instantiate providers and run pipeline
    try:
        claude_client = ClaudeClient()
        tts_provider = OpenAITTSProvider()
        image_provider = OpenAIImageProvider()
        caption_provider = OpenAIWhisperProvider()

        run_pipeline(
            state,
            claude_client=claude_client,
            tts_provider=tts_provider,
            image_provider=image_provider,
            caption_provider=caption_provider,
        )
        _display_outcome(state)
    except Exception as exc:
        console.print(Panel(str(exc), title="Error", style="red"))
        raise typer.Exit(1)
```

**Run:** `pytest tests/test_cli.py -v`
Expected: All resume tests pass.

**Commit:** `git add src/story_video/cli.py tests/test_cli.py && git commit -m "feat(cli): implement resume command — load project and continue pipeline"`

---

## Task 4: `estimate` Command

**Files:**
- Modify: `src/story_video/cli.py`
- Modify: `tests/test_cli.py`

The `estimate` command calculates cost without creating a project. It shares many flags with `create` but only needs mode + config options to compute projected costs.

### Tests to write

```python
class TestEstimateCommand:
    """story-video estimate — show cost estimate."""

    def test_estimate_adapt(self):
        """Adapt mode estimate displays cost breakdown."""
        result = runner.invoke(app, [
            "estimate",
            "--mode", "adapt",
        ])

        assert result.exit_code == 0
        assert "cost estimate" in result.output.lower()
        assert "claude" in result.output.lower()
        assert "$" in result.output

    def test_estimate_original(self):
        """Original mode works for estimate (all modes supported)."""
        result = runner.invoke(app, [
            "estimate",
            "--mode", "original",
        ])

        assert result.exit_code == 0
        assert "cost estimate" in result.output.lower()

    def test_estimate_with_duration_override(self):
        """--duration affects the estimate."""
        result = runner.invoke(app, [
            "estimate",
            "--mode", "adapt",
            "--duration", "60",
        ])

        assert result.exit_code == 0
        assert "60 minutes" in result.output

    def test_estimate_does_not_create_project(self, tmp_path):
        """Estimate is read-only — no project directory created."""
        result = runner.invoke(app, [
            "estimate",
            "--mode", "adapt",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code == 0
        # No directories created
        assert list(tmp_path.iterdir()) == []
```

### Implementation

```python
@app.command()
def estimate(
    mode: str = typer.Option(..., help="Input mode: original, inspired_by, or adapt"),
    duration: int | None = typer.Option(None, help="Target duration in minutes"),
    voice: str | None = typer.Option(None, help="TTS voice name (affects cost)"),
    config: Path | None = typer.Option(None, help="Path to config.yaml"),
) -> None:
    """Show cost estimate without starting generation."""
    try:
        input_mode = InputMode(mode)
    except ValueError:
        console.print(f"[red]Unknown mode: {mode}. Choose from: adapt, original, inspired_by[/red]")
        raise typer.Exit(1)

    # Build config with CLI overrides
    cli_overrides: dict[str, Any] = {}
    if duration is not None:
        cli_overrides["story.target_duration_minutes"] = duration
    if voice is not None:
        cli_overrides["tts.voice"] = voice

    app_config = load_config(
        config_path=config,
        cli_overrides=cli_overrides if cli_overrides else None,
    )

    cost = estimate_cost(input_mode, app_config)
    formatted = format_cost_estimate(cost)
    console.print(Panel(formatted, title="Cost Estimate", style="cyan"))
```

**Run:** `pytest tests/test_cli.py -v`
Expected: All estimate tests pass.

**Commit:** `git add src/story_video/cli.py tests/test_cli.py && git commit -m "feat(cli): implement estimate command — projected cost display"`

---

## Task 5: `status` and `list` Commands

**Files:**
- Modify: `src/story_video/cli.py`
- Modify: `tests/test_cli.py`

Both commands are read-only displays using Rich tables. `status` shows a single project's details. `list` shows all projects in the output directory.

### Tests to write

```python
class TestStatusCommand:
    """story-video status — show project state."""

    def test_status_with_project_id(self, tmp_path):
        """Displays project metadata and scene status."""
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

        result = runner.invoke(app, [
            "status",
            "status-test",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code == 0
        assert "status-test" in result.output
        assert "adapt" in result.output.lower()

    def test_status_no_id_uses_most_recent(self, tmp_path):
        """No project ID → shows most recent project."""
        ProjectState.create(
            project_id="latest-project",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )

        result = runner.invoke(app, [
            "status",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code == 0
        assert "latest-project" in result.output

    def test_status_no_projects(self, tmp_path):
        """Empty output dir → error message."""
        result = runner.invoke(app, [
            "status",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code != 0
        assert "no project" in result.output.lower()


class TestListCommand:
    """story-video list — show all projects."""

    def test_list_shows_projects(self, tmp_path):
        """Lists all projects with metadata."""
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

        result = runner.invoke(app, [
            "list",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code == 0
        assert "project-a" in result.output
        assert "project-b" in result.output

    def test_list_empty(self, tmp_path):
        """No projects → clean message."""
        result = runner.invoke(app, [
            "list",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code == 0
        assert "no project" in result.output.lower()

    def test_list_skips_corrupted(self, tmp_path):
        """Corrupted project.json skipped, valid projects shown."""
        # Good project
        ProjectState.create(
            project_id="good-project",
            mode=InputMode.ADAPT,
            config=AppConfig(),
            output_dir=tmp_path,
        )
        # Bad project
        bad = tmp_path / "bad-project"
        bad.mkdir()
        (bad / "project.json").write_text("{broken", encoding="utf-8")

        result = runner.invoke(app, [
            "list",
            "--output-dir", str(tmp_path),
        ])

        assert result.exit_code == 0
        assert "good-project" in result.output
```

### Implementation

```python
@app.command()
def status(
    project_id: str | None = typer.Argument(None, help="Project ID (default: most recent)"),
    output_dir: Path = typer.Option(Path("./output"), help="Output directory"),
) -> None:
    """Show current state of a project."""
    # Find project
    if project_id:
        project_dir = output_dir / project_id
    else:
        project_dir = _find_most_recent_project(output_dir)

    if project_dir is None or not (project_dir / "project.json").exists():
        name = project_id or "any"
        console.print(f"[red]No project found: {name} in {output_dir}[/red]")
        raise typer.Exit(1)

    state = ProjectState.load(project_dir)
    meta = state.metadata

    # Project info panel
    info_lines = [
        f"Project:  {meta.project_id}",
        f"Mode:     {meta.mode.value}",
        f"Phase:    {meta.current_phase.value if meta.current_phase else 'not started'}",
        f"Status:   {meta.status.value}",
        f"Created:  {meta.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Scenes:   {len(meta.scenes)}",
    ]
    console.print(Panel("\n".join(info_lines), title="Project Status", style="cyan"))

    # Scene asset table (if scenes exist)
    if meta.scenes:
        table = Table(title="Scene Assets")
        table.add_column("Scene", style="bold")
        table.add_column("Text")
        table.add_column("Narration")
        table.add_column("Img Prompt")
        table.add_column("Audio")
        table.add_column("Image")
        table.add_column("Captions")
        table.add_column("Video")

        for scene in meta.scenes:
            s = scene.asset_status
            table.add_row(
                f"{scene.scene_number}. {scene.title}",
                _status_icon(s.text),
                _status_icon(s.narration_text),
                _status_icon(s.image_prompt),
                _status_icon(s.audio),
                _status_icon(s.image),
                _status_icon(s.captions),
                _status_icon(s.video_segment),
            )

        console.print(table)


def _status_icon(status: SceneStatus) -> str:
    """Map scene status to a colored icon for Rich table display."""
    icons = {
        SceneStatus.COMPLETED: "[green]done[/green]",
        SceneStatus.IN_PROGRESS: "[yellow]...[/yellow]",
        SceneStatus.FAILED: "[red]FAIL[/red]",
        SceneStatus.PENDING: "[dim]--[/dim]",
    }
    return icons.get(status, str(status.value))


@app.command(name="list")
def list_projects(
    output_dir: Path = typer.Option(Path("./output"), help="Output directory"),
) -> None:
    """List all projects."""
    if not output_dir.exists():
        console.print("No projects found.")
        return

    projects: list[dict] = []
    for child in sorted(output_dir.iterdir()):
        if not child.is_dir():
            continue
        json_path = child / "project.json"
        if not json_path.exists():
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            projects.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    if not projects:
        console.print("No projects found.")
        return

    # Sort by created_at descending (newest first)
    projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)

    table = Table(title="Projects")
    table.add_column("Project ID", style="bold")
    table.add_column("Mode")
    table.add_column("Phase")
    table.add_column("Status")
    table.add_column("Created")

    for p in projects:
        created = p.get("created_at", "")[:10]  # YYYY-MM-DD
        table.add_row(
            p.get("project_id", "?"),
            p.get("mode", "?"),
            p.get("current_phase") or "not started",
            p.get("status", "?"),
            created,
        )

    console.print(table)
```

**Run:** `pytest tests/test_cli.py -v`
Expected: All status and list tests pass.

**Commit:** `git add src/story_video/cli.py tests/test_cli.py && git commit -m "feat(cli): implement status and list commands — Rich table display"`

---

## Task 6: Documentation and Cleanup

**Files:**
- Modify: `VERSION_HISTORY.md`
- Modify: `CHANGELOG.md`
- Modify: `BUGS_AND_TODOS.md`
- Modify: `docs/plans/2026-02-15-cli-implementation.md` (mark status Complete)

### Updates

**VERSION_HISTORY.md:**
- Update test count
- Add CLI entries to Added section under Unreleased

**CHANGELOG.md:**
- Add under `[Unreleased] > Added`:
  - CLI commands fully implemented — create (adapt mode), resume, estimate, status, list with Rich output

**BUGS_AND_TODOS.md:**
- Move CLI item from Backlog to Resolved

**Plan status:**
- Change `**Status:** Pending` to `**Status:** Complete`

**Commit:** `git add -f VERSION_HISTORY.md CHANGELOG.md BUGS_AND_TODOS.md docs/plans/2026-02-15-cli-implementation.md && git commit -m "docs: update tracking files for CLI implementation"`

---

## Retrospective

(To be filled in after implementation)

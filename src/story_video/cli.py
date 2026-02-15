"""CLI entry point for story-video."""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel

from story_video.config import load_config
from story_video.cost import estimate_cost, format_cost_estimate
from story_video.models import InputMode, PhaseStatus
from story_video.pipeline.caption_generator import OpenAIWhisperProvider
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.image_generator import OpenAIImageProvider
from story_video.pipeline.orchestrator import run_pipeline
from story_video.pipeline.tts_generator import OpenAITTSProvider
from story_video.state import ProjectState

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="story-video",
    help="Generate narrated story videos for YouTube.",
    no_args_is_help=True,
)

console = Console()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _generate_project_id(mode: str, output_dir: Path) -> str:
    """Generate a collision-safe project ID.

    Format: ``{mode}-{YYYY-MM-DD}``. When a directory with that name already
    exists in *output_dir*, appends ``-2``, ``-3``, etc. until a free name is
    found.  If *output_dir* doesn't exist yet, no collision is possible so the
    base name is returned immediately.

    Args:
        mode: Input mode string (e.g. "adapt", "original", "inspired_by").
        output_dir: Base output directory where project directories live.

    Returns:
        A project ID string guaranteed not to collide with existing directories.
    """
    today = date.today().isoformat()
    base = f"{mode}-{today}"

    if not output_dir.exists():
        return base

    if not (output_dir / base).exists():
        return base

    suffix = 2
    while (output_dir / f"{base}-{suffix}").exists():
        suffix += 1
    return f"{base}-{suffix}"


def _read_text_input(value: str) -> str:
    """Read text from a file path or return inline text.

    If *value* is a path to an existing file, reads and returns its content.
    Otherwise returns *value* unchanged (treated as inline text).

    Args:
        value: Either a filesystem path or inline text.

    Returns:
        The file content if *value* pointed to a file, or *value* itself.
    """
    path = Path(value)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return value


def _find_most_recent_project(output_dir: Path) -> Path | None:
    """Find the most recently created project in *output_dir*.

    Scans subdirectories for ``project.json`` files, reads the ``created_at``
    field via lightweight ``json.loads`` (no full Pydantic validation), and
    returns the path to the directory whose project has the latest timestamp.

    Silently skips directories without ``project.json`` and files with
    corrupted JSON.

    Args:
        output_dir: Base output directory to scan.

    Returns:
        Path to the most recent project directory, or ``None`` if no valid
        projects are found (or if *output_dir* does not exist).
    """
    if not output_dir.is_dir():
        return None

    most_recent_path: Path | None = None
    most_recent_timestamp: str = ""

    for child in output_dir.iterdir():
        if not child.is_dir():
            continue

        json_path = child / "project.json"
        if not json_path.exists():
            continue

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            created_at = data["created_at"]
        except (json.JSONDecodeError, KeyError, OSError):
            logger.debug("Skipping %s: invalid or unreadable project.json", child)
            continue

        if created_at > most_recent_timestamp:
            most_recent_timestamp = created_at
            most_recent_path = child

    return most_recent_path


def _display_outcome(state: ProjectState) -> None:
    """Display a Rich panel summarising the project outcome.

    Panel style depends on the project's current status:

    - **COMPLETED** -- green "Success" panel with the video directory path.
    - **AWAITING_REVIEW** -- yellow "Paused for Review" panel with the phase
      name and resume instructions.
    - **FAILED** -- red "Error" panel with the phase name and retry
      instructions.

    Args:
        state: The project state to display.
    """
    status = state.metadata.status
    phase = state.metadata.current_phase

    if status == PhaseStatus.COMPLETED:
        video_dir = state.project_dir / "video"
        console.print(
            Panel(
                f"Project complete! Video files are in:\n{video_dir}",
                title="Success",
                border_style="green",
            )
        )
    elif status == PhaseStatus.AWAITING_REVIEW:
        phase_name = phase.value if phase else "unknown"
        console.print(
            Panel(
                f"Paused for review at phase: {phase_name}\n"
                f"Run [bold]story-video resume[/bold] to continue.",
                title="Paused for Review",
                border_style="yellow",
            )
        )
    elif status == PhaseStatus.FAILED:
        phase_name = phase.value if phase else "unknown"
        console.print(
            Panel(
                f"Failed at phase: {phase_name}\nRun [bold]story-video resume[/bold] to retry.",
                title="Error",
                border_style="red",
            )
        )


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


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
    # --- Validate mode ---
    try:
        input_mode = InputMode(mode)
    except ValueError:
        console.print(
            Panel(
                f"Unknown mode: '{mode}'. Valid modes: adapt, original, inspired_by",
                title="Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    if input_mode in (InputMode.ORIGINAL, InputMode.INSPIRED_BY):
        console.print(
            Panel(
                f"Mode '{mode}' is not yet implemented. Only 'adapt' is currently supported.",
                title="Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    # --- Validate adapt requires --source-material ---
    if input_mode == InputMode.ADAPT and source_material is None:
        console.print(
            Panel(
                "Adapt mode requires --source-material (path to file or inline text).",
                title="Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    # --- Build config overrides ---
    cli_overrides: dict[str, Any] = {}
    if voice is not None:
        cli_overrides["tts.voice"] = voice
    if duration is not None:
        cli_overrides["story.target_duration_minutes"] = duration
    if autonomous:
        cli_overrides["pipeline.autonomous"] = True

    # --- Load config ---
    try:
        app_config = load_config(config_path=config, cli_overrides=cli_overrides)
    except Exception as exc:
        console.print(Panel(str(exc), title="Configuration Error", border_style="red"))
        raise typer.Exit(1)

    # --- Create project ---
    project_id = _generate_project_id(mode, output_dir)

    try:
        state = ProjectState.create(project_id, input_mode, app_config, output_dir)
    except Exception as exc:
        console.print(Panel(str(exc), title="Project Creation Error", border_style="red"))
        raise typer.Exit(1)

    # --- Write source material ---
    if source_material is not None:
        text = _read_text_input(source_material)
        (state.project_dir / "source_story.txt").write_text(text, encoding="utf-8")

    console.print(f"Created project {project_id}")

    # --- Instantiate providers and run pipeline ---
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
    except Exception as exc:
        console.print(Panel(str(exc), title="Pipeline Error", border_style="red"))
        raise typer.Exit(1)

    _display_outcome(state)


@app.command()
def resume(
    project_id: str | None = typer.Argument(
        None, help="Project ID to resume (default: most recent)"
    ),
    output_dir: Path = typer.Option(Path("./output"), help="Output directory"),
) -> None:
    """Resume a paused or failed project."""
    # --- Resolve project directory ---
    if project_id is not None:
        project_dir = output_dir / project_id
        if not (project_dir / "project.json").exists():
            console.print(
                Panel(
                    f"Project '{project_id}' not found in {output_dir}",
                    title="Error",
                    border_style="red",
                )
            )
            raise typer.Exit(1)
    else:
        project_dir = _find_most_recent_project(output_dir)
        if project_dir is None:
            console.print(
                Panel(
                    f"No projects found in {output_dir}",
                    title="Error",
                    border_style="red",
                )
            )
            raise typer.Exit(1)

    # --- Load project state ---
    try:
        state = ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as exc:
        console.print(Panel(str(exc), title="Load Error", border_style="red"))
        raise typer.Exit(1)

    console.print(f"Resuming project {state.metadata.project_id}")

    # --- Instantiate providers and run pipeline ---
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
    except Exception as exc:
        console.print(Panel(str(exc), title="Pipeline Error", border_style="red"))
        raise typer.Exit(1)

    _display_outcome(state)


@app.command()
def estimate(
    mode: str = typer.Option(..., help="Input mode: original, inspired_by, or adapt"),
    duration: int | None = typer.Option(None, help="Target duration in minutes"),
    voice: str | None = typer.Option(None, help="TTS voice name (affects cost)"),
    config: Path | None = typer.Option(None, help="Path to config.yaml"),
) -> None:
    """Show cost estimate without starting generation."""
    # --- Validate mode ---
    try:
        input_mode = InputMode(mode)
    except ValueError:
        console.print(
            Panel(
                f"Unknown mode: '{mode}'. Valid modes: adapt, original, inspired_by",
                title="Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    # --- Build config overrides ---
    cli_overrides: dict[str, Any] = {}
    if duration is not None:
        cli_overrides["story.target_duration_minutes"] = duration
    if voice is not None:
        cli_overrides["tts.voice"] = voice

    # --- Load config ---
    try:
        app_config = load_config(config_path=config, cli_overrides=cli_overrides)
    except Exception as exc:
        console.print(Panel(str(exc), title="Configuration Error", border_style="red"))
        raise typer.Exit(1)

    # --- Calculate and display cost estimate ---
    cost = estimate_cost(input_mode, app_config)
    formatted = format_cost_estimate(cost)

    console.print(Panel(formatted, title="Cost Estimate", border_style="cyan"))


@app.command()
def status(project_id: str | None = typer.Argument(None)) -> None:
    """Show current state of a project."""
    typer.echo("Not yet implemented.")


@app.command()
def list_projects() -> None:
    """List all projects."""
    typer.echo("Not yet implemented.")


if __name__ == "__main__":
    app()

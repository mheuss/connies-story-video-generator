"""CLI entry point for story-video."""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from story_video.config import load_config
from story_video.cost import estimate_cost, format_cost_estimate
from story_video.models import InputMode, PhaseStatus, SceneStatus
from story_video.pipeline.caption_generator import OpenAIWhisperProvider
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.image_generator import OpenAIImageProvider
from story_video.pipeline.orchestrator import run_pipeline
from story_video.pipeline.tts_generator import ElevenLabsTTSProvider, OpenAITTSProvider
from story_video.state import ProjectState

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="story-video",
    no_args_is_help=True,
)


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Generate narrated story videos for YouTube."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(name)s %(levelname)s: %(message)s",
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
    if path.is_dir():
        msg = f"'{value}' is a directory, not a file. Provide a file path or inline text."
        raise ValueError(msg)
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

    - **COMPLETED** -- green "Success" panel with the final video file path.
    - **AWAITING_REVIEW** -- yellow "Paused for Review" panel with the phase
      name and resume instructions.
    - **FAILED** -- red "Error" panel with the phase name and retry
      instructions.
    - Any other status -- dim "Info" panel with the raw status value.

    Args:
        state: The project state to display.
    """
    status = state.metadata.status
    phase = state.metadata.current_phase

    if status == PhaseStatus.COMPLETED:
        video_path = state.project_dir / "final.mp4"
        console.print(
            Panel(
                f"Project complete! Video is at:\n{video_path}",
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
    else:
        console.print(
            Panel(
                f"Pipeline status: {status.value}",
                title="Info",
                border_style="dim",
            )
        )


def _status_icon(status: SceneStatus) -> str:
    """Map scene status to a colored icon for Rich table display.

    Args:
        status: The scene asset status to display.

    Returns:
        A Rich-markup string with color-coded status text.
    """
    icons = {
        SceneStatus.COMPLETED: "[green]done[/green]",
        SceneStatus.IN_PROGRESS: "[yellow]...[/yellow]",
        SceneStatus.FAILED: "[red]FAIL[/red]",
        SceneStatus.PENDING: "[dim]--[/dim]",
    }
    return icons.get(status, str(status.value))


def _make_tts_provider(provider_name: str) -> OpenAITTSProvider | ElevenLabsTTSProvider:
    """Instantiate the TTS provider by name.

    Args:
        provider_name: Provider identifier from config (openai, elevenlabs).

    Returns:
        An instantiated TTS provider.

    Raises:
        typer.Exit: If the provider name is not recognized.
    """
    if provider_name == "openai":
        return OpenAITTSProvider()
    if provider_name == "elevenlabs":
        return ElevenLabsTTSProvider()
    console.print(
        Panel(
            f"Unknown TTS provider: '{provider_name}'. Supported providers: openai, elevenlabs",
            title="Configuration Error",
            border_style="red",
        )
    )
    raise typer.Exit(1)


def _run_with_providers(state: ProjectState) -> None:
    """Instantiate all providers and run the pipeline.

    Args:
        state: Project state to pass to the pipeline.

    Raises:
        Exception: Any pipeline error is re-raised.
    """
    tts_provider = _make_tts_provider(state.metadata.config.tts.provider)
    claude_client = ClaudeClient()
    image_provider = OpenAIImageProvider()
    caption_provider = OpenAIWhisperProvider()

    run_pipeline(
        state,
        claude_client=claude_client,
        tts_provider=tts_provider,
        image_provider=image_provider,
        caption_provider=caption_provider,
    )


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@app.command()
def create(
    mode: str = typer.Option(..., help="Input mode: adapt, original, inspired_by"),
    input: str | None = typer.Option(
        None, "--input", help="Source story, creative brief, or path to file"
    ),
    premise: str | None = typer.Option(
        None, help="Optional creative direction for inspired_by mode"
    ),
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

    # --- Validate input required ---
    if input is None:
        console.print(
            Panel(
                f"Mode '{mode}' requires --input (path to file or inline text).",
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
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        console.print(Panel(str(exc), title="Configuration Error", border_style="red"))
        raise typer.Exit(1)

    # --- Create project ---
    project_id = _generate_project_id(mode, output_dir)

    try:
        state = ProjectState.create(project_id, input_mode, app_config, output_dir)
    except FileExistsError as exc:
        console.print(Panel(str(exc), title="Project Creation Error", border_style="red"))
        raise typer.Exit(1)

    # --- Write source material ---
    text = _read_text_input(input)
    (state.project_dir / "source_story.txt").write_text(text, encoding="utf-8")

    # --- Write premise ---
    if premise is not None:
        if input_mode in (InputMode.INSPIRED_BY, InputMode.ORIGINAL):
            (state.project_dir / "premise.txt").write_text(premise, encoding="utf-8")
        else:
            logger.warning("--premise is only used with inspired_by or original modes; ignoring")

    console.print(f"Created project {project_id}")

    # --- Instantiate providers and run pipeline ---
    try:
        _run_with_providers(state)
    except Exception as exc:
        logger.exception("Pipeline failed")
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
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        console.print(Panel(str(exc), title="Load Error", border_style="red"))
        raise typer.Exit(1)

    console.print(f"Resuming project {state.metadata.project_id}")

    # --- Instantiate providers and run pipeline ---
    try:
        _run_with_providers(state)
    except Exception as exc:
        logger.exception("Pipeline failed")
        console.print(Panel(str(exc), title="Pipeline Error", border_style="red"))
        raise typer.Exit(1)

    _display_outcome(state)


@app.command()
def estimate(
    mode: str = typer.Option(..., help="Input mode: original, inspired_by, or adapt"),
    duration: int | None = typer.Option(None, help="Target duration in minutes"),
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
    # --- Load config ---
    try:
        app_config = load_config(config_path=config, cli_overrides=cli_overrides)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        console.print(Panel(str(exc), title="Configuration Error", border_style="red"))
        raise typer.Exit(1)

    # --- Calculate and display cost estimate ---
    cost = estimate_cost(input_mode, app_config)
    formatted = format_cost_estimate(cost)

    console.print(Panel(formatted, title="Cost Estimate", border_style="cyan"))


@app.command()
def status(
    project_id: str | None = typer.Argument(None, help="Project ID (default: most recent)"),
    output_dir: Path = typer.Option(Path("./output"), help="Output directory"),
) -> None:
    """Show current state of a project."""
    # --- Resolve project directory ---
    if project_id is not None:
        project_dir = output_dir / project_id
    else:
        project_dir = _find_most_recent_project(output_dir)

    if project_dir is None or not (project_dir / "project.json").exists():
        console.print(
            Panel(
                "No project found.",
                title="Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    # --- Load project state ---
    try:
        state = ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        console.print(Panel(str(exc), title="Load Error", border_style="red"))
        raise typer.Exit(1)

    meta = state.metadata
    phase_name = meta.current_phase.value if meta.current_phase else "none"
    created_str = meta.created_at.isoformat()[:10]
    scene_count = len(meta.scenes)

    # --- Project info panel ---
    info_lines = (
        f"[bold]Project:[/bold] {meta.project_id}\n"
        f"[bold]Mode:[/bold] {meta.mode.value}\n"
        f"[bold]Phase:[/bold] {phase_name}\n"
        f"[bold]Status:[/bold] {meta.status.value}\n"
        f"[bold]Created:[/bold] {created_str}\n"
        f"[bold]Scenes:[/bold] {scene_count}"
    )
    console.print(Panel(info_lines, title="Project Status", border_style="cyan"))

    # --- Scene asset status table ---
    if meta.scenes:
        table = Table(title="Scene Asset Status")
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


@app.command(name="list")
def list_projects(
    output_dir: Path = typer.Option(Path("./output"), help="Output directory"),
) -> None:
    """List all projects."""
    if not output_dir.is_dir():
        console.print("No projects found.")
        return

    # --- Scan for projects with lightweight JSON parse ---
    projects: list[dict[str, str]] = []

    for child in output_dir.iterdir():
        if not child.is_dir():
            continue

        json_path = child / "project.json"
        if not json_path.exists():
            continue

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            projects.append(
                {
                    "project_id": data.get("project_id", child.name),
                    "mode": data.get("mode", "unknown"),
                    "current_phase": data.get("current_phase") or "none",
                    "status": data.get("status", "unknown"),
                    "created_at": data.get("created_at", ""),
                }
            )
        except (json.JSONDecodeError, KeyError, OSError):
            logger.debug("Skipping %s: invalid or unreadable project.json", child)
            continue

    if not projects:
        console.print("No projects found.")
        return

    # --- Sort by created_at descending (newest first) ---
    projects.sort(key=lambda p: p["created_at"], reverse=True)

    # --- Display Rich table ---
    table = Table(title="Projects")
    table.add_column("Project ID", style="bold")
    table.add_column("Mode")
    table.add_column("Phase")
    table.add_column("Status")
    table.add_column("Created")

    for proj in projects:
        table.add_row(
            proj["project_id"],
            proj["mode"],
            proj["current_phase"],
            proj["status"],
            proj["created_at"][:10],
        )

    console.print(table)


if __name__ == "__main__":
    app()

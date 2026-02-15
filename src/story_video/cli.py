"""CLI entry point for story-video."""

import json
import logging
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from story_video.models import PhaseStatus
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
# CLI commands (stubs — will be replaced in later tasks)
# ---------------------------------------------------------------------------


@app.command()
def create() -> None:
    """Start a new story video project."""
    typer.echo("Not yet implemented.")


@app.command()
def resume(project_id: str | None = typer.Argument(None)) -> None:
    """Resume a paused or failed project."""
    typer.echo("Not yet implemented.")


@app.command()
def estimate() -> None:
    """Show cost estimate without starting generation."""
    typer.echo("Not yet implemented.")


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

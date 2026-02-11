"""CLI entry point for story-video."""

import typer

app = typer.Typer(
    name="story-video",
    help="Generate narrated story videos for YouTube.",
    no_args_is_help=True,
)


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

"""FastAPI application factory.

Creates and configures the FastAPI app with all route groups
mounted under the /api/v1 prefix.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI

from story_video.web import routes_artifacts, routes_pipeline, routes_projects, routes_settings

__all__ = ["create_app"]

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


def create_app(
    *,
    env_path: Path | None = None,
    output_dir: Path | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        env_path: Path to the .env file for API key storage.
            Defaults to None (uses the module-level default in routes_settings).
        output_dir: Base directory for project storage.
            Defaults to None (uses the module-level default in routes_projects).

    Returns:
        Configured FastAPI instance with all routes mounted.
    """
    if env_path is not None:
        routes_settings.configure(env_path)
    if output_dir is not None:
        routes_projects.configure(output_dir)
        routes_pipeline.configure(output_dir)
        routes_artifacts.configure(output_dir)

    app = FastAPI(title="Story Video", version="0.1.0")
    app.include_router(router)
    app.include_router(routes_settings.router)
    app.include_router(routes_projects.router)
    app.include_router(routes_pipeline.router)
    app.include_router(routes_artifacts.router)
    return app

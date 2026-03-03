"""FastAPI application factory.

Creates and configures the FastAPI app with all route groups
mounted under the /api/v1 prefix. Optionally serves a static
SPA frontend when a static_dir is provided.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from story_video.web import (
    routes_artifacts,
    routes_pipeline,
    routes_projects,
    routes_settings,
    routes_tts,
)

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
    static_dir: Path | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        env_path: Path to the .env file for API key storage.
            Defaults to None (uses the module-level default in routes_settings).
        output_dir: Base directory for project storage.
            Defaults to None (uses the module-level default in routes_projects).
        static_dir: Directory containing the built SPA frontend.
            When provided and the directory exists, mounts /assets for
            hashed JS/CSS bundles and adds a catch-all route that serves
            index.html for SPA client-side routing. When None, the app
            is API-only (used during development).

    Returns:
        Configured FastAPI instance with all routes mounted.
    """
    if env_path is not None:
        routes_settings.configure(env_path)
    routes_settings.load_env()

    if output_dir is not None:
        routes_projects.configure(output_dir)
        routes_artifacts.configure(output_dir)
        routes_tts.configure(output_dir)

    app = FastAPI(title="Story Video", version="0.1.0")

    # API routers first so /api/v1/* is never shadowed by the catch-all.
    app.include_router(router)
    app.include_router(routes_settings.router)
    app.include_router(routes_projects.router)
    app.include_router(routes_pipeline.router)
    app.include_router(routes_artifacts.router)
    app.include_router(routes_tts.router)

    # Static file serving for the SPA frontend.
    if static_dir is not None and static_dir.is_dir():
        assets_dir = static_dir / "assets"
        index_html = static_dir / "index.html"

        if assets_dir.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="static-assets",
            )

        if index_html.is_file():

            @app.get("/{full_path:path}")
            async def spa_catch_all(full_path: str) -> FileResponse:
                """Serve index.html for all non-API paths (SPA routing)."""
                return FileResponse(str(index_html))

    return app

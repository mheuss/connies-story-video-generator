"""FastAPI application factory.

Creates and configures the FastAPI app with all route groups
mounted under the /api/v1 prefix.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI

from story_video.web import routes_settings

__all__ = ["create_app"]

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


def create_app(*, env_path: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        env_path: Path to the .env file for API key storage.
            Defaults to None (uses the module-level default in routes_settings).

    Returns:
        Configured FastAPI instance with all routes mounted.
    """
    if env_path is not None:
        routes_settings.configure(env_path)

    app = FastAPI(title="Story Video", version="0.1.0")
    app.include_router(router)
    app.include_router(routes_settings.router)
    return app

"""FastAPI application factory.

Creates and configures the FastAPI app with all route groups
mounted under the /api/v1 prefix.
"""

from fastapi import APIRouter, FastAPI

__all__ = ["create_app"]

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance with all routes mounted.
    """
    app = FastAPI(title="Story Video", version="0.1.0")
    app.include_router(router)
    return app

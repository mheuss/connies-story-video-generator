"""Settings routes -- API key management.

Provides endpoints to check API key status and set/update keys.
Keys are written to a .env file and loaded into the process environment.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_env_path: Path = Path(".env")


def configure(env_path: Path) -> None:
    """Set the .env file path. Called by create_app()."""
    global _env_path  # noqa: PLW0603
    _env_path = env_path


def load_env() -> None:
    """Load API keys from the .env file into the process environment."""
    load_dotenv(_env_path, override=False)


@router.get("/api-keys")
async def get_api_key_status() -> dict:
    """Check which API keys are configured in the environment."""
    return {
        "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
        "openai_configured": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        "elevenlabs_configured": bool(os.environ.get("ELEVENLABS_API_KEY", "").strip()),
    }


class ApiKeyUpdate(BaseModel):
    """Request body for updating API keys."""

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    elevenlabs_api_key: str | None = None

    @field_validator("anthropic_api_key", "openai_api_key", "elevenlabs_api_key", mode="before")
    @classmethod
    def reject_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            msg = "Key value must not be blank"
            raise ValueError(msg)
        return v


@router.post("/api-keys")
async def set_api_keys(body: ApiKeyUpdate) -> dict:
    """Set or update API keys."""
    if (
        body.anthropic_api_key is None
        and body.openai_api_key is None
        and body.elevenlabs_api_key is None
    ):
        raise HTTPException(status_code=422, detail="At least one key must be provided")

    if body.anthropic_api_key is not None:
        os.environ["ANTHROPIC_API_KEY"] = body.anthropic_api_key
    if body.openai_api_key is not None:
        os.environ["OPENAI_API_KEY"] = body.openai_api_key
    if body.elevenlabs_api_key is not None:
        os.environ["ELEVENLABS_API_KEY"] = body.elevenlabs_api_key

    _write_env_file()
    return {"status": "ok"}


def _write_env_file() -> None:
    """Write current API keys to the .env file."""
    lines = []
    anthropic = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    elevenlabs = os.environ.get("ELEVENLABS_API_KEY", "")
    if anthropic:
        lines.append(f"ANTHROPIC_API_KEY={anthropic}")
    if openai_key:
        lines.append(f"OPENAI_API_KEY={openai_key}")
    if elevenlabs:
        lines.append(f"ELEVENLABS_API_KEY={elevenlabs}")
    _env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

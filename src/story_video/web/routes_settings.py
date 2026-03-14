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
    def reject_blank_or_unsafe(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            msg = "Key value must not be blank"
            raise ValueError(msg)
        if v is not None and any(c in v for c in ("\n", "\r", "\x00")):
            msg = "Key value must not contain control characters"
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


def _quote_env_value(v: str) -> str:
    """Quote a value for safe .env file storage."""
    escaped = v.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


_MANAGED_KEYS = frozenset({"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"})


def _write_env_file() -> None:
    """Write current API keys to the .env file, preserving unmanaged content."""
    # Collect current values for managed keys
    managed: dict[str, str] = {}
    for key in _MANAGED_KEYS:
        value = os.environ.get(key, "")
        if value:
            managed[key] = value

    # Read existing file and update managed lines in place
    written_keys: set[str] = set()
    output_lines: list[str] = []
    if _env_path.exists():
        for line in _env_path.read_text(encoding="utf-8").splitlines():
            key_name = line.split("=", 1)[0].strip() if "=" in line else ""
            if key_name in _MANAGED_KEYS:
                if key_name in managed:
                    output_lines.append(f"{key_name}={_quote_env_value(managed[key_name])}")
                    written_keys.add(key_name)
                # else: key was unset, drop the line
            else:
                output_lines.append(line)

    # Append any managed keys that weren't in the original file
    for key in sorted(managed.keys() - written_keys):
        output_lines.append(f"{key}={_quote_env_value(managed[key])}")

    _env_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

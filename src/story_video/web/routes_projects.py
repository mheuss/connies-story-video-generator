"""Project CRUD routes.

Handles project creation, status queries, and deletion.
All state is managed through ProjectState (project.json on disk).
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from story_video.config import load_config
from story_video.models import InputMode
from story_video.state import ProjectState

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

_output_dir: Path = Path("./output")


def configure(output_dir: Path) -> None:
    """Set the output directory. Called by create_app()."""
    global _output_dir  # noqa: PLW0603
    _output_dir = output_dir


class CreateProjectRequest(BaseModel):
    """Request body for project creation."""

    mode: str
    source_text: str
    autonomous: bool = False

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        try:
            InputMode(v)
        except ValueError:
            valid = ", ".join(m.value for m in InputMode)
            msg = f"Invalid mode '{v}'. Must be one of: {valid}"
            raise ValueError(msg) from None
        return v

    @field_validator("source_text")
    @classmethod
    def validate_source_text(cls, v: str) -> str:
        if not v.strip():
            msg = "source_text must not be empty"
            raise ValueError(msg)
        max_bytes = 10 * 1024 * 1024  # 10 MB
        if len(v.encode("utf-8")) > max_bytes:
            msg = "source_text exceeds 10 MB limit"
            raise ValueError(msg)
        return v


def _generate_project_id(mode: str) -> str:
    """Generate a unique project ID like 'adapt-2026-02-25'."""
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    base_id = f"{mode}-{date_str}"
    if not (_output_dir / base_id).exists():
        return base_id
    for n in range(2, 100):
        candidate = f"{base_id}-{n}"
        if not (_output_dir / candidate).exists():
            return candidate
    raise HTTPException(status_code=409, detail=f"Too many projects for {date_str}")


@router.post("", status_code=201)
async def create_project(body: CreateProjectRequest) -> dict:
    """Create a new story video project."""
    mode = InputMode(body.mode)
    config = load_config(None)
    config = config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update={"autonomous": body.autonomous})}
    )

    project_id = _generate_project_id(body.mode)
    _output_dir.mkdir(parents=True, exist_ok=True)
    state = ProjectState.create(project_id, mode, config, _output_dir)

    source_path = state.project_dir / "source_story.txt"
    source_path.write_text(body.source_text, encoding="utf-8")

    return {
        "project_id": project_id,
        "mode": body.mode,
        "project_dir": str(state.project_dir),
    }


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict:
    """Get project status and metadata."""
    state = _load_project(project_id)
    meta = state.metadata
    return {
        "project_id": meta.project_id,
        "mode": meta.mode.value,
        "status": meta.status.value,
        "current_phase": meta.current_phase.value if meta.current_phase else None,
        "scene_count": len(meta.scenes),
        "created_at": meta.created_at.isoformat(),
    }


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> dict:
    """Delete a project and all its files."""
    project_dir = _resolve_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    shutil.rmtree(project_dir)
    return {"status": "deleted", "project_id": project_id}


def _resolve_project_dir(project_id: str) -> Path:
    """Resolve and validate a project directory path.

    Rejects path traversal attempts (e.g. ``../../etc``) by verifying
    the resolved path stays within ``_output_dir``.
    """
    project_dir = (_output_dir / project_id).resolve()
    if not project_dir.is_relative_to(_output_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid project ID")
    return project_dir


def _load_project(project_id: str) -> ProjectState:
    """Load a ProjectState by ID, raising 404 if not found."""
    project_dir = _resolve_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    try:
        return ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

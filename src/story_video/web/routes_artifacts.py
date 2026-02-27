"""Artifact serving and editing routes.

Serves pipeline-generated files (JSON, images, audio, video) from
the project directory. Supports inline editing of text/JSON artifacts.
"""

import json
import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from story_video.models import PipelinePhase
from story_video.state import ProjectState

logger = logging.getLogger(__name__)

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/projects", tags=["artifacts"])

_output_dir: Path = Path("./output")

# Map pipeline phases to the subdirectory where their artifacts live.
# Empty string means project root (for phases that produce project-level JSON).
_PHASE_DIRS: dict[str, str] = {
    "analysis": "",
    "story_bible": "",
    "outline": "",
    "scene_prose": "scenes",
    "critique_revision": "scenes",
    "scene_splitting": "scenes",
    "narration_flagging": "scenes",
    "image_prompts": "scenes",
    "narration_prep": "scenes",
    "tts_generation": "audio",
    "image_generation": "images",
    "caption_generation": "captions",
    "video_assembly": "",
}

# For phases that map to a shared directory (e.g. project root), restrict
# the listing to only the file(s) that phase actually produces.
_PHASE_FILE_FILTER: dict[str, set[str]] = {
    "analysis": {"analysis.json"},
    "story_bible": {"story_bible.json"},
    "outline": {"outline.json"},
    "video_assembly": {"final.mp4"},
}


def configure(output_dir: Path) -> None:
    """Set the output directory. Called by create_app()."""
    global _output_dir  # noqa: PLW0603
    _output_dir = output_dir


def _validate_phase(phase: str) -> str:
    """Validate that the phase string is a known PipelinePhase value."""
    try:
        PipelinePhase(phase)
    except ValueError:
        valid = ", ".join(p.value for p in PipelinePhase)
        raise HTTPException(
            status_code=422,
            detail=f"Invalid phase '{phase}'. Must be one of: {valid}",
        ) from None
    return phase


def _resolve_artifact_dir(project_id: str, phase: str) -> Path:
    """Resolve the artifact directory for a project/phase combination."""
    project_dir = _output_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    _validate_phase(phase)
    subdir = _PHASE_DIRS.get(phase, "scenes")
    return project_dir / subdir if subdir else project_dir


def _guard_path_traversal(base_dir: Path, filename: str) -> Path:
    """Resolve filename within base_dir, rejecting path traversal."""
    resolved = (base_dir / filename).resolve()
    if not resolved.is_relative_to(base_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename (path traversal)")
    return resolved


def _export_image_prompts(project_dir: Path) -> None:
    """Write image prompts from project state as editable JSON files.

    Creates one file per scene (image_prompts_scene_NNN.json) in the scenes
    directory. Only writes files that don't already exist, so manual edits
    are preserved.
    """
    try:
        state = ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        logger.warning("Failed to load project state for image prompt export: %s", project_dir)
        return
    scenes_dir = project_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    for scene in state.metadata.scenes:
        if not scene.image_prompts:
            continue
        filename = f"image_prompts_scene_{scene.scene_number:03d}.json"
        path = scenes_dir / filename
        if path.exists():
            continue
        data = [{"key": p.key, "prompt": p.prompt} for p in scene.image_prompts]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@router.get("/{project_id}/artifacts/{phase}")
async def list_artifacts(project_id: str, phase: str) -> dict:
    """List artifact files for a pipeline phase."""
    project_dir = _output_dir / project_id
    if phase == "image_prompts" and project_dir.exists():
        _export_image_prompts(project_dir)
    artifact_dir = _resolve_artifact_dir(project_id, phase)
    if not artifact_dir.exists():
        return {"files": []}
    allowed = _PHASE_FILE_FILTER.get(phase)
    if phase == "image_prompts":
        allowed = {
            f.name
            for f in artifact_dir.iterdir()
            if f.is_file() and f.name.startswith("image_prompts_scene_")
        }
    files = []
    for path in sorted(artifact_dir.iterdir()):
        if path.is_file() and (allowed is None or path.name in allowed):
            mime, _ = mimetypes.guess_type(path.name)
            files.append(
                {
                    "name": path.name,
                    "size": path.stat().st_size,
                    "content_type": mime or "application/octet-stream",
                }
            )
    return {"files": files}


@router.get("/{project_id}/artifacts/{phase}/{filename}")
async def get_artifact(project_id: str, phase: str, filename: str) -> FileResponse:
    """Serve a specific artifact file."""
    artifact_dir = _resolve_artifact_dir(project_id, phase)
    file_path = _guard_path_traversal(artifact_dir, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    mime, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(file_path, media_type=mime or "application/octet-stream")


class UpdateArtifactRequest(BaseModel):
    """Request body for updating an artifact."""

    content: str

    @field_validator("content")
    @classmethod
    def reject_blank(cls, v: str) -> str:
        if not v.strip():
            msg = "Content must not be blank"
            raise ValueError(msg)
        return v


@router.put("/{project_id}/artifacts/{phase}/{filename}")
async def update_artifact(
    project_id: str, phase: str, filename: str, body: UpdateArtifactRequest
) -> dict:
    """Update the contents of a text/JSON artifact."""
    artifact_dir = _resolve_artifact_dir(project_id, phase)
    file_path = _guard_path_traversal(artifact_dir, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    file_path.write_text(body.content, encoding="utf-8")
    return {"status": "updated", "filename": filename}

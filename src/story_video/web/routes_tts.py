"""TTS scene review routes.

Provides scene metadata for the TTS review UI, including narration text,
audio file status, and URLs for playback via the existing artifact endpoint.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from story_video.models import Scene, SceneStatus
from story_video.pipeline.tts_generator import generate_audio
from story_video.state import ProjectState
from story_video.utils.narration_tags import parse_story_header
from story_video.web import pipeline_runner
from story_video.web.pipeline_runner import _make_tts_provider

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["tts"])

_output_dir: Path = Path("./output")


def configure(output_dir: Path) -> None:
    """Set the output directory for project resolution. Called by create_app()."""
    global _output_dir  # noqa: PLW0603
    _output_dir = output_dir


class NarrationTextUpdate(BaseModel):
    """Request body for updating a scene's narration text."""

    narration_text: str


def _resolve_project_dir(project_id: str) -> Path:
    """Resolve and validate a project directory path.

    Rejects path traversal attempts (e.g. ``../../etc``) by verifying
    the resolved path stays within ``_output_dir``.
    """
    project_dir = (_output_dir / project_id).resolve()
    if not project_dir.is_relative_to(_output_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid project ID")
    return project_dir


def _build_scene_response(
    scene: Scene, project_id: str, state: ProjectState, project_dir: Path
) -> dict:
    """Build the standard TTS scene response dict.

    Centralises the response shape used by the list, regenerate, and
    update-narration-text endpoints so any schema change only needs
    updating in one place.
    """
    ext = state.metadata.config.tts.file_extension
    audio_filename = f"scene_{scene.scene_number:03d}.{ext}"
    audio_path = project_dir / "audio" / audio_filename
    return {
        "scene_number": scene.scene_number,
        "title": scene.title,
        "narration_text": scene.narration_text,
        "audio_file": audio_filename,
        "audio_url": f"/api/v1/projects/{project_id}/artifacts/tts_generation/{audio_filename}",
        "has_audio": audio_path.is_file(),
    }


@router.get("/{project_id}/tts-scenes")
async def list_tts_scenes(project_id: str) -> dict:
    """List scene metadata for TTS review.

    Returns each scene's number, title, narration text, audio filename,
    a URL for streaming the audio via the artifact endpoint, and whether
    the audio file exists on disk.

    Args:
        project_id: The project identifier.

    Returns:
        Dict with a ``scenes`` list containing scene TTS metadata.

    Raises:
        HTTPException 404: If the project directory does not exist.
    """
    project_dir = _resolve_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        state = ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    scenes = [
        _build_scene_response(scene, project_id, state, project_dir)
        for scene in state.metadata.scenes
    ]
    return {"scenes": scenes}


@router.post("/{project_id}/tts-scenes/{scene_number}/regenerate")
async def regenerate_tts_scene(project_id: str, scene_number: int) -> dict:
    """Regenerate TTS audio for a single scene.

    Re-runs the TTS provider for the specified scene, replacing any
    existing audio file. Useful when narration text has been edited
    or a different voice/mood result is desired.

    Args:
        project_id: The project identifier.
        scene_number: 1-based scene number to regenerate audio for.

    Returns:
        Dict with updated scene metadata: scene_number, title,
        narration_text, audio_file, audio_url, and has_audio.

    Raises:
        HTTPException 404: If the project or scene does not exist.
        HTTPException 409: If the pipeline is currently running.
        HTTPException 500: If audio generation fails.
    """
    if pipeline_runner.is_running():
        raise HTTPException(
            status_code=409,
            detail="Cannot regenerate audio while the pipeline is running",
        )

    project_dir = _resolve_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        state = ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # Find scene by number
    scene = None
    for s in state.metadata.scenes:
        if s.scene_number == scene_number:
            scene = s
            break
    if scene is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scene {scene_number} not found in project {project_id}",
        )

    # Parse story header from source_story.txt if it exists
    story_header = None
    source_story_path = project_dir / "source_story.txt"
    if source_story_path.is_file():
        try:
            source_text = source_story_path.read_text(encoding="utf-8")
            story_header, _ = parse_story_header(source_text)
        except (OSError, ValueError):
            story_header = None

    # Instantiate TTS provider
    provider_name = state.metadata.config.tts.provider
    provider = _make_tts_provider(provider_name)

    # Reset audio asset status to PENDING so generate_audio can proceed.
    # Direct attribute assignment bypasses the "never overwrite completed"
    # invariant in update_scene_asset, which is intentional for regeneration.
    scene.asset_status.audio = SceneStatus.PENDING

    try:
        generate_audio(scene, state, provider, story_header=story_header)
    except Exception as exc:
        logger.exception(
            "TTS regeneration failed for project %s scene %d", project_id, scene_number
        )
        raise HTTPException(
            status_code=500,
            detail=f"Audio generation failed for scene {scene_number}: {exc}",
        ) from exc

    state.save()

    return _build_scene_response(scene, project_id, state, project_dir)


@router.put("/{project_id}/tts-scenes/{scene_number}/narration-text")
async def update_narration_text(
    project_id: str, scene_number: int, body: NarrationTextUpdate
) -> dict:
    """Update narration text for a scene before TTS regeneration.

    Replaces the narration text for the specified scene and persists
    the change to disk. This is typically done before regenerating
    TTS audio so the new text is used for speech synthesis.

    Args:
        project_id: The project identifier.
        scene_number: 1-based scene number to update.
        body: Request body containing the new ``narration_text``.

    Returns:
        Dict with updated scene metadata: scene_number, title,
        narration_text, audio_file, audio_url, and has_audio.

    Raises:
        HTTPException 404: If the project or scene does not exist.
        HTTPException 422: If narration_text is blank or whitespace-only.
    """
    if not body.narration_text.strip():
        raise HTTPException(
            status_code=422,
            detail="narration_text must not be blank or whitespace-only",
        )

    project_dir = _resolve_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    try:
        state = ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # Find scene by number
    scene = None
    for s in state.metadata.scenes:
        if s.scene_number == scene_number:
            scene = s
            break
    if scene is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scene {scene_number} not found in project {project_id}",
        )

    scene.narration_text = body.narration_text
    state.save()

    return _build_scene_response(scene, project_id, state, project_dir)

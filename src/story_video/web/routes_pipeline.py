"""Pipeline control routes -- start, approve, and progress streaming."""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from story_video.models import PhaseStatus
from story_video.state import ProjectState
from story_video.web import pipeline_runner
from story_video.web.progress import ProgressBridge

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/projects", tags=["pipeline"])

_output_dir: Path = Path("./output")


def configure(output_dir: Path) -> None:
    """Set the output directory. Called by create_app()."""
    global _output_dir  # noqa: PLW0603
    _output_dir = output_dir


def get_bridge() -> ProgressBridge | None:
    """Return the current ProgressBridge. Thin wrapper for test mocking."""
    return pipeline_runner.get_bridge()


@router.post("/{project_id}/start", status_code=202)
async def start_pipeline(project_id: str) -> dict:
    """Start or resume the pipeline for a project."""
    state = _load_project(project_id)

    if state.metadata.status == PhaseStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    pipeline_runner.run_pipeline_in_thread(state)
    return {"status": "started", "project_id": project_id}


@router.post("/{project_id}/approve", status_code=202)
async def approve_checkpoint(project_id: str) -> dict:
    """Approve the current checkpoint and resume the pipeline."""
    state = _load_project(project_id)

    if state.metadata.status != PhaseStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"Project is not awaiting review (status: {state.metadata.status.value})",
        )

    pipeline_runner.run_pipeline_in_thread(state)
    return {"status": "approved", "project_id": project_id}


@router.get("/{project_id}/progress")
async def stream_progress(project_id: str) -> EventSourceResponse:
    """Stream pipeline progress events via SSE."""
    _verify_project_exists(project_id)
    return EventSourceResponse(_event_generator())


_TERMINAL_EVENTS = frozenset({"completed", "error"})


async def _event_generator():
    """Yield SSE events from the bridge until a terminal event."""
    while True:
        bridge = get_bridge()
        if bridge is None:
            await asyncio.sleep(0.5)
            continue
        event = bridge.try_get(timeout=0.1)
        if event is not None:
            yield {"event": event.event, "data": json.dumps(event.data)}
            if event.event in _TERMINAL_EVENTS:
                return
        else:
            await asyncio.sleep(0.1)


def _verify_project_exists(project_id: str) -> None:
    """Raise 404 if the project directory does not exist."""
    project_dir = _output_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")


def _load_project(project_id: str) -> ProjectState:
    """Load a ProjectState by ID, raising 404 if not found."""
    project_dir = _output_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    try:
        return ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

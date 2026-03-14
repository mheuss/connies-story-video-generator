"""Pipeline control routes -- start, approve, and progress streaming."""

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from story_video.models import PhaseStatus
from story_video.web import pipeline_runner
from story_video.web.progress import TERMINAL_EVENTS, ProgressBridge
from story_video.web.routes_projects import _load_project, _resolve_project_dir

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/projects", tags=["pipeline"])


def get_bridge() -> ProgressBridge | None:
    """Return the current ProgressBridge. Thin wrapper for test mocking."""
    return pipeline_runner.get_bridge()


@router.post("/{project_id}/start", status_code=202)
async def start_pipeline(project_id: str) -> dict:
    """Start or resume the pipeline for a project."""
    if pipeline_runner.is_running():
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    state = _load_project(project_id)

    if state.metadata.status == PhaseStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    pipeline_runner.run_pipeline_in_thread(state)
    return {"status": "started", "project_id": project_id}


class ApproveRequest(BaseModel):
    """Optional request body for the approve endpoint."""

    auto: bool = False


@router.post("/{project_id}/approve", status_code=202)
async def approve_checkpoint(project_id: str, body: ApproveRequest | None = None) -> dict:
    """Approve the current checkpoint and resume the pipeline."""
    state = _load_project(project_id)

    if state.metadata.status != PhaseStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"Project is not awaiting review (status: {state.metadata.status.value})",
        )

    if body and body.auto:
        new_pipeline = state.metadata.config.pipeline.model_copy(update={"autonomous": True})
        new_config = state.metadata.config.model_copy(update={"pipeline": new_pipeline})
        state.metadata.config = new_config
        state.save()

    pipeline_runner.run_pipeline_in_thread(state)
    return {"status": "approved", "project_id": project_id}


@router.get("/{project_id}/progress")
async def stream_progress(project_id: str) -> EventSourceResponse:
    """Stream pipeline progress events via SSE."""
    _verify_project_exists(project_id)
    return EventSourceResponse(_event_generator())


_BRIDGE_WAIT_TIMEOUT = 120.0


async def _event_generator():
    """Yield SSE events from the bridge until a terminal event."""
    deadline = time.monotonic() + _BRIDGE_WAIT_TIMEOUT
    bridge = None
    while True:
        if bridge is None:
            bridge = get_bridge()
        if bridge is None:
            if time.monotonic() >= deadline:
                if pipeline_runner.is_running():
                    msg = "Pipeline is running but not streaming progress (timed out)"
                else:
                    msg = "Pipeline is not running (timed out)"
                yield {
                    "event": "error",
                    "data": json.dumps({"message": msg}),
                }
                return
            await asyncio.sleep(0.5)
            continue
        event = bridge.try_get(timeout=0.1)
        if event is not None:
            yield {"event": event.event, "data": json.dumps(event.data)}
            if event.event in TERMINAL_EVENTS:
                return
        else:
            if not bridge.is_done and not pipeline_runner.is_running():
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "Pipeline terminated unexpectedly"}),
                }
                return
            await asyncio.sleep(0.1)


def _verify_project_exists(project_id: str) -> None:
    """Raise 404 if the project directory does not exist."""
    project_dir = _resolve_project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

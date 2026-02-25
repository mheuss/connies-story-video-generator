"""Background pipeline execution.

Wraps run_pipeline() in a thread so the API can return immediately.
Manages a single active pipeline run (one at a time by design).
"""

import logging
import threading

from story_video.models import PhaseStatus
from story_video.pipeline.caption_generator import OpenAIWhisperProvider
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.image_generator import OpenAIImageProvider
from story_video.pipeline.orchestrator import run_pipeline
from story_video.pipeline.tts_generator import (
    ElevenLabsTTSProvider,
    OpenAITTSProvider,
)
from story_video.state import ProjectState
from story_video.web.progress import ProgressBridge, ProgressEvent

__all__ = ["get_bridge", "is_running", "run_pipeline_in_thread"]

logger = logging.getLogger(__name__)

_active_thread: threading.Thread | None = None
_active_bridge: ProgressBridge | None = None
_lock = threading.Lock()


def is_running() -> bool:
    """Check if a pipeline is currently running."""
    with _lock:
        return _active_thread is not None and _active_thread.is_alive()


def get_bridge() -> ProgressBridge | None:
    """Return the current ProgressBridge, or None if no pipeline is active."""
    with _lock:
        return _active_bridge


def run_pipeline_in_thread(state: ProjectState) -> ProgressBridge:
    """Start the pipeline in a background thread.

    Args:
        state: Project state to run the pipeline on.

    Returns:
        The ProgressBridge for streaming events to the client.

    Raises:
        RuntimeError: If a pipeline is already running.
    """
    global _active_thread, _active_bridge  # noqa: PLW0603
    with _lock:
        if _active_thread is not None and _active_thread.is_alive():
            msg = "A pipeline is already running"
            raise RuntimeError(msg)

        bridge = ProgressBridge()
        _active_bridge = bridge

        thread = threading.Thread(
            target=_run_pipeline_safe,
            args=(state, bridge),
            daemon=True,
        )
        _active_thread = thread
        thread.start()

    return bridge


def _make_tts_provider(
    provider_name: str,
) -> OpenAITTSProvider | ElevenLabsTTSProvider:
    """Instantiate a TTS provider by name."""
    if provider_name == "elevenlabs":
        return ElevenLabsTTSProvider()
    return OpenAITTSProvider()


def _run_pipeline_safe(state: ProjectState, bridge: ProgressBridge) -> None:
    """Run the pipeline, catching and logging exceptions.

    After the pipeline returns (or raises), reloads state from disk
    to determine the terminal event: checkpoint, completed, or error.
    """
    try:
        tts_provider = _make_tts_provider(state.metadata.config.tts.provider)
        run_pipeline(
            state,
            claude_client=ClaudeClient(),
            tts_provider=tts_provider,
            image_provider=OpenAIImageProvider(),
            caption_provider=OpenAIWhisperProvider(),
        )
        # Reload state from disk to detect checkpoint vs completion.
        refreshed = ProjectState.load(state.project_dir)
        if refreshed.metadata.status == PhaseStatus.AWAITING_REVIEW:
            bridge.push(
                ProgressEvent(
                    event="checkpoint",
                    data={"phase": refreshed.metadata.current_phase},
                )
            )
        else:
            bridge.push(ProgressEvent(event="completed", data={}))
    except Exception:
        logger.exception("Pipeline failed for project %s", state.metadata.project_id)
        bridge.push(
            ProgressEvent(
                event="error",
                data={"message": f"Pipeline failed for project {state.metadata.project_id}"},
            )
        )

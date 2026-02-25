"""Background pipeline execution.

Wraps run_pipeline() in a thread so the API can return immediately.
Manages a single active pipeline run (one at a time by design).
"""

import logging
import threading

from story_video.pipeline.caption_generator import OpenAIWhisperProvider
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.image_generator import OpenAIImageProvider
from story_video.pipeline.orchestrator import run_pipeline
from story_video.pipeline.tts_generator import (
    ElevenLabsTTSProvider,
    OpenAITTSProvider,
)
from story_video.state import ProjectState

__all__ = ["is_running", "run_pipeline_in_thread"]

logger = logging.getLogger(__name__)

_active_thread: threading.Thread | None = None
_lock = threading.Lock()


def is_running() -> bool:
    """Check if a pipeline is currently running."""
    with _lock:
        return _active_thread is not None and _active_thread.is_alive()


def run_pipeline_in_thread(state: ProjectState) -> None:
    """Start the pipeline in a background thread.

    Args:
        state: Project state to run the pipeline on.

    Raises:
        RuntimeError: If a pipeline is already running.
    """
    global _active_thread  # noqa: PLW0603
    with _lock:
        if _active_thread is not None and _active_thread.is_alive():
            msg = "A pipeline is already running"
            raise RuntimeError(msg)

        thread = threading.Thread(
            target=_run_pipeline_safe,
            args=(state,),
            daemon=True,
        )
        _active_thread = thread
        thread.start()


def _make_tts_provider(
    provider_name: str,
) -> OpenAITTSProvider | ElevenLabsTTSProvider:
    """Instantiate a TTS provider by name."""
    if provider_name == "elevenlabs":
        return ElevenLabsTTSProvider()
    return OpenAITTSProvider()


def _run_pipeline_safe(state: ProjectState) -> None:
    """Run the pipeline, catching and logging exceptions."""
    try:
        tts_provider = _make_tts_provider(state.metadata.config.tts.provider)
        run_pipeline(
            state,
            claude_client=ClaudeClient(),
            tts_provider=tts_provider,
            image_provider=OpenAIImageProvider(),
            caption_provider=OpenAIWhisperProvider(),
        )
    except Exception:
        logger.exception("Pipeline failed for project %s", state.metadata.project_id)

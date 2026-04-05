"""Tests for story_video.web.pipeline_runner — background pipeline execution."""

import threading
from unittest.mock import MagicMock, patch

import pytest

import story_video.web.pipeline_runner as runner
from story_video.pipeline.tts_generator import ElevenLabsTTSProvider, OpenAITTSProvider
from story_video.web.pipeline_runner import (
    _make_tts_provider,
    get_bridge,
    is_running,
    run_pipeline_in_thread,
)


@pytest.fixture(autouse=True)
def _reset_globals():
    """Clear module-level globals before and after each test."""
    with runner._lock:
        runner._active_thread = None
        runner._active_bridge = None
    yield
    with runner._lock:
        runner._active_thread = None
        runner._active_bridge = None


# ---------------------------------------------------------------------------
# Task 1 (M-3): _make_tts_provider validation
# ---------------------------------------------------------------------------


class TestMakeTTSProvider:
    """_make_tts_provider returns the correct provider or raises for unknowns."""

    def test_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        provider = _make_tts_provider("openai")
        assert isinstance(provider, OpenAITTSProvider)

    def test_elevenlabs(self):
        provider = _make_tts_provider("elevenlabs")
        assert isinstance(provider, ElevenLabsTTSProvider)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown TTS provider: 'typo'"):
            _make_tts_provider("typo")


# ---------------------------------------------------------------------------
# Task 2 (H-2): Globals cleared after pipeline finishes
# ---------------------------------------------------------------------------


class TestGlobalsClearedAfterPipeline:
    """_run_pipeline_safe clears _active_thread and _active_bridge in finally."""

    def test_globals_cleared_after_success(self):
        """After a successful pipeline run, is_running() is False and get_bridge() is None."""
        mock_state = MagicMock()
        mock_state.metadata.config.tts.provider = "openai"
        mock_state.metadata.project_id = "test-project"

        with (
            patch.object(runner, "run_pipeline") as mock_run,
            patch.object(runner, "ClaudeClient"),
            patch.object(runner, "OpenAIImageProvider"),
            patch.object(runner, "OpenAIWhisperProvider"),
            patch.object(runner, "_make_tts_provider"),
        ):
            mock_run.return_value = None
            # Mock ProjectState.load to return a completed state
            with patch.object(runner, "ProjectState") as mock_ps:
                mock_ps.load.return_value = mock_state

                run_pipeline_in_thread(mock_state)
                # Wait for the thread to finish
                runner._active_thread.join(timeout=5)

        assert not is_running()
        assert get_bridge() is None

    def test_globals_cleared_after_error(self):
        """After a pipeline crash, is_running() is False and get_bridge() is None."""
        mock_state = MagicMock()
        mock_state.metadata.config.tts.provider = "openai"
        mock_state.metadata.project_id = "test-project"

        with (
            patch.object(runner, "run_pipeline") as mock_run,
            patch.object(runner, "ClaudeClient"),
            patch.object(runner, "OpenAIImageProvider"),
            patch.object(runner, "OpenAIWhisperProvider"),
            patch.object(runner, "_make_tts_provider"),
        ):
            mock_run.side_effect = RuntimeError("boom")

            run_pipeline_in_thread(mock_state)
            runner._active_thread.join(timeout=5)

        assert not is_running()
        assert get_bridge() is None


# ---------------------------------------------------------------------------
# Task 3 (H-3): Remaining pipeline_runner coverage
# ---------------------------------------------------------------------------


class TestRunPipelineInThread:
    """run_pipeline_in_thread guards against concurrent runs."""

    def test_raises_if_already_running(self):
        """Cannot start a second pipeline while one is running."""
        alive_thread = MagicMock(spec=threading.Thread)
        alive_thread.is_alive.return_value = True
        with runner._lock:
            runner._active_thread = alive_thread

        with pytest.raises(RuntimeError, match="A pipeline is already running"):
            run_pipeline_in_thread(MagicMock())


class TestIsRunning:
    """is_running reflects thread liveness accurately."""

    def test_false_when_no_thread(self):
        assert not is_running()

    def test_false_when_thread_dead(self):
        dead_thread = MagicMock(spec=threading.Thread)
        dead_thread.is_alive.return_value = False
        with runner._lock:
            runner._active_thread = dead_thread

        assert not is_running()


class TestErrorEventContent:
    """Error event pushed to the bridge includes actionable exception details."""

    def test_error_event_includes_exception_details(self):
        """Error event pushed to bridge includes exception type and message."""
        mock_state = MagicMock()
        mock_state.metadata.config.tts.provider = "openai"
        mock_state.metadata.project_id = "test-project"

        pushed_events = []

        with (
            patch.object(runner, "run_pipeline") as mock_run,
            patch.object(runner, "ClaudeClient"),
            patch.object(runner, "OpenAIImageProvider"),
            patch.object(runner, "OpenAIWhisperProvider"),
            patch.object(runner, "_make_tts_provider"),
            patch("story_video.web.pipeline_runner.ProgressBridge") as MockBridge,
        ):
            mock_bridge_instance = MockBridge.return_value
            mock_bridge_instance.push.side_effect = lambda evt: pushed_events.append(evt)

            mock_run.side_effect = RuntimeError("something broke")
            run_pipeline_in_thread(mock_state)
            thread = runner._active_thread
            if thread is not None:
                thread.join(timeout=5)

        error_events = [e for e in pushed_events if e.event == "error"]
        assert len(error_events) == 1
        assert "RuntimeError" in error_events[0].data["message"]
        assert "something broke" in error_events[0].data["message"]

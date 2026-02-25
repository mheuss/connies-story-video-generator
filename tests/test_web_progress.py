"""Tests for story_video.web.progress — SSE progress bridge."""

from story_video.web.progress import ProgressBridge, ProgressEvent


class TestProgressEvent:
    """ProgressEvent formats as SSE message."""

    def test_format_sse_event(self):
        event = ProgressEvent(event="phase_started", data={"phase": "analysis"})
        formatted = event.format_sse()
        assert "event: phase_started" in formatted
        assert '"phase": "analysis"' in formatted


class TestProgressBridge:
    """ProgressBridge queues events and yields them for SSE."""

    def test_push_and_receive_event(self):
        bridge = ProgressBridge()
        bridge.push(ProgressEvent(event="phase_started", data={"phase": "analysis"}))
        event = bridge.try_get(timeout=0.1)
        assert event is not None
        assert event.event == "phase_started"
        assert event.data["phase"] == "analysis"

    def test_try_get_returns_none_on_empty(self):
        bridge = ProgressBridge()
        event = bridge.try_get(timeout=0.01)
        assert event is None

    def test_multiple_events_in_order(self):
        bridge = ProgressBridge()
        bridge.push(ProgressEvent(event="phase_started", data={"phase": "analysis"}))
        bridge.push(ProgressEvent(event="scene_progress", data={"scene": 1}))
        bridge.push(ProgressEvent(event="completed", data={"video": "final.mp4"}))

        events = []
        for _ in range(3):
            e = bridge.try_get(timeout=0.1)
            assert e is not None
            events.append(e.event)
        assert events == ["phase_started", "scene_progress", "completed"]

    def test_push_completed_marks_done(self):
        bridge = ProgressBridge()
        assert not bridge.is_done
        bridge.push(ProgressEvent(event="completed", data={}))
        assert bridge.is_done

    def test_push_error_marks_done(self):
        bridge = ProgressBridge()
        bridge.push(ProgressEvent(event="error", data={"message": "fail"}))
        assert bridge.is_done

"""Tests for story_video.web.progress — SSE progress bridge."""

from story_video.web.progress import TERMINAL_EVENTS, ProgressBridge, ProgressEvent


class TestProgressEvent:
    """ProgressEvent dataclass behavior."""

    def test_event_fields(self):
        """ProgressEvent stores event type and data dict."""
        event = ProgressEvent(event="phase_started", data={"phase": "analysis"})
        assert event.event == "phase_started"
        assert event.data == {"phase": "analysis"}

    def test_default_data_is_empty_dict(self):
        """ProgressEvent data defaults to empty dict."""
        event = ProgressEvent(event="completed")
        assert event.data == {}


class TestProgressBridge:
    """ProgressBridge thread-safe queue behavior."""

    def test_push_and_get(self):
        """Pushed event can be retrieved via try_get."""
        bridge = ProgressBridge()
        event = ProgressEvent(event="phase_started", data={"phase": "analysis"})
        bridge.push(event)
        result = bridge.try_get(timeout=0.1)
        assert result is event

    def test_try_get_returns_none_on_empty(self):
        """Empty bridge returns None after timeout."""
        bridge = ProgressBridge()
        result = bridge.try_get(timeout=0.01)
        assert result is None

    def test_terminal_event_sets_is_done(self):
        """Pushing a terminal event sets is_done to True."""
        for event_type in TERMINAL_EVENTS:
            bridge = ProgressBridge()
            assert bridge.is_done is False
            bridge.push(ProgressEvent(event=event_type))
            assert bridge.is_done is True

    def test_non_terminal_event_leaves_is_done_false(self):
        """Pushing a non-terminal event does not set is_done."""
        bridge = ProgressBridge()
        bridge.push(ProgressEvent(event="phase_started"))
        bridge.push(ProgressEvent(event="scene_progress"))
        assert bridge.is_done is False

    def test_events_are_delivered_in_fifo_order(self):
        """Events are retrieved in the same order they were pushed."""
        bridge = ProgressBridge()
        first = ProgressEvent(event="phase_started", data={"phase": "analysis"})
        second = ProgressEvent(event="scene_progress", data={"scene": 1})
        third = ProgressEvent(event="completed")

        bridge.push(first)
        bridge.push(second)
        bridge.push(third)

        assert bridge.try_get(timeout=0.1) is first
        assert bridge.try_get(timeout=0.1) is second
        assert bridge.try_get(timeout=0.1) is third

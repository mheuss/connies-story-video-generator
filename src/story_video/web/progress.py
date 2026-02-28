"""SSE progress bridge.

Connects the synchronous pipeline thread to the async SSE endpoint
via a thread-safe queue. The pipeline pushes ProgressEvents; the
SSE endpoint reads and streams them to the client.
"""

import queue
from dataclasses import dataclass, field

__all__ = ["ProgressBridge", "ProgressEvent"]

TERMINAL_EVENTS = frozenset({"completed", "error", "checkpoint"})


@dataclass
class ProgressEvent:
    """A single progress event to stream via SSE.

    Attributes:
        event: SSE event type (phase_started, scene_progress, checkpoint, completed, error).
        data: Event payload as a dictionary.
    """

    event: str
    data: dict = field(default_factory=dict)


class ProgressBridge:
    """Thread-safe bridge between pipeline thread and SSE endpoint."""

    def __init__(self) -> None:
        self._queue: queue.Queue[ProgressEvent] = queue.Queue()
        self._done = False

    @property
    def is_done(self) -> bool:
        """Whether a terminal event (completed/error) has been pushed."""
        return self._done

    def push(self, event: ProgressEvent) -> None:
        """Push an event onto the queue."""
        if event.event in TERMINAL_EVENTS:
            self._done = True
        self._queue.put(event)

    def try_get(self, timeout: float = 0.5) -> ProgressEvent | None:
        """Try to get an event from the queue.

        Returns None if the queue is empty after timeout.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

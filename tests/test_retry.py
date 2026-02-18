"""Tests for story_video.utils.retry — Retry decorators with tenacity.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the retry utilities.
"""

import logging

import pytest
from tenacity import RetryError

from story_video.utils.retry import RetryError as ReexportedRetryError
from story_video.utils.retry import with_retry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TrackedCallable:
    """A callable that tracks invocation count and can be configured to fail N times."""

    def __init__(self, fail_times: int = 0, exception: type[Exception] = RuntimeError):
        self.call_count = 0
        self.fail_times = fail_times
        self.exception = exception

    def __call__(self) -> str:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise self.exception(f"Failure #{self.call_count}")
        return "success"


# ---------------------------------------------------------------------------
# with_retry — basic behavior
# ---------------------------------------------------------------------------


class TestWithRetryBasicBehavior:
    """with_retry decorator — wraps functions with exponential backoff retry."""

    def test_succeeds_on_first_try_no_retry(self):
        """When the function succeeds immediately, no retries occur."""
        tracker = TrackedCallable(fail_times=0)

        @with_retry(retry_on=(RuntimeError,), max_retries=3, base_delay=0.01)
        def fn():
            return tracker()

        result = fn()
        assert result == "success"
        assert tracker.call_count == 1

    def test_fails_then_succeeds_on_retry(self):
        """When the function fails once then succeeds, retry recovers."""
        tracker = TrackedCallable(fail_times=1)

        @with_retry(retry_on=(RuntimeError,), max_retries=3, base_delay=0.01)
        def fn():
            return tracker()

        result = fn()
        assert result == "success"
        assert tracker.call_count == 2

    def test_fails_twice_then_succeeds(self):
        """When the function fails twice then succeeds, retry recovers."""
        tracker = TrackedCallable(fail_times=2)

        @with_retry(retry_on=(RuntimeError,), max_retries=3, base_delay=0.01)
        def fn():
            return tracker()

        result = fn()
        assert result == "success"
        assert tracker.call_count == 3

    def test_exhausts_all_retries_raises_original_exception(self):
        """When all attempts fail, the original exception is re-raised.

        Total calls = max_retries + 1.
        """
        tracker = TrackedCallable(fail_times=100)

        @with_retry(retry_on=(RuntimeError,), max_retries=3, base_delay=0.01)
        def fn():
            return tracker()

        with pytest.raises(RuntimeError):
            fn()
        # 1 initial + 3 retries = 4 total
        assert tracker.call_count == 4

    def test_preserves_return_value(self):
        """The decorated function returns the original function's return value."""

        @with_retry(retry_on=(Exception,), max_retries=1, base_delay=0.01)
        def fn():
            return {"key": "value", "number": 42}

        assert fn() == {"key": "value", "number": 42}


# ---------------------------------------------------------------------------
# with_retry — custom parameters
# ---------------------------------------------------------------------------


class TestWithRetryCustomParameters:
    """with_retry respects custom max_retries and base_delay."""

    def test_custom_max_retries_one(self):
        """max_retries=1 means 1 initial + 1 retry = 2 total attempts."""
        tracker = TrackedCallable(fail_times=100)

        @with_retry(retry_on=(RuntimeError,), max_retries=1, base_delay=0.01)
        def fn():
            return tracker()

        with pytest.raises(RuntimeError):
            fn()
        assert tracker.call_count == 2

    def test_custom_max_retries_five(self):
        """max_retries=5 means 1 initial + 5 retries = 6 total attempts."""
        tracker = TrackedCallable(fail_times=100)

        @with_retry(retry_on=(RuntimeError,), max_retries=5, base_delay=0.01)
        def fn():
            return tracker()

        with pytest.raises(RuntimeError):
            fn()
        assert tracker.call_count == 6

    def test_custom_max_retries_zero_no_retry(self):
        """max_retries=0 means only 1 attempt, no retries."""
        tracker = TrackedCallable(fail_times=1)

        @with_retry(retry_on=(RuntimeError,), max_retries=0, base_delay=0.01)
        def fn():
            return tracker()

        with pytest.raises(RuntimeError):
            fn()
        assert tracker.call_count == 1

    def test_succeeds_on_last_retry(self):
        """Function succeeds on the very last allowed attempt."""
        tracker = TrackedCallable(fail_times=3)

        @with_retry(retry_on=(RuntimeError,), max_retries=3, base_delay=0.01)
        def fn():
            return tracker()

        result = fn()
        assert result == "success"
        assert tracker.call_count == 4


# ---------------------------------------------------------------------------
# with_retry — retry_on exception filtering
# ---------------------------------------------------------------------------


class TestWithRetryExceptionFiltering:
    """with_retry only retries on specified exception types."""

    def test_retries_on_specified_exception_type(self):
        """When retry_on matches the raised exception, retry occurs."""
        tracker = TrackedCallable(fail_times=1, exception=ValueError)

        @with_retry(max_retries=3, base_delay=0.01, retry_on=(ValueError,))
        def fn():
            return tracker()

        result = fn()
        assert result == "success"
        assert tracker.call_count == 2

    def test_does_not_retry_on_unspecified_exception_type(self):
        """When the exception type doesn't match retry_on, it propagates immediately."""
        tracker = TrackedCallable(fail_times=1, exception=TypeError)

        @with_retry(max_retries=3, base_delay=0.01, retry_on=(ValueError,))
        def fn():
            return tracker()

        with pytest.raises(TypeError, match="Failure #1"):
            fn()
        assert tracker.call_count == 1

    def test_retries_on_multiple_specified_exception_types(self):
        """When retry_on contains multiple types, all are retried."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01, retry_on=(ValueError, OSError))
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first")
            if call_count == 2:
                raise OSError("second")
            return "success"

        result = fn()
        assert result == "success"
        assert call_count == 3

    def test_retry_on_is_required(self):
        """Omitting retry_on raises TypeError — no silent catch-all default."""
        with pytest.raises(TypeError):
            with_retry(max_retries=3, base_delay=0.01)


# ---------------------------------------------------------------------------
# with_retry — logging
# ---------------------------------------------------------------------------


class TestWithRetryLogging:
    """with_retry logs retry attempts."""

    def test_logs_on_retry(self, caplog):
        """Each retry attempt produces a log message."""
        tracker = TrackedCallable(fail_times=2)

        @with_retry(retry_on=(RuntimeError,), max_retries=3, base_delay=0.01)
        def fn():
            return tracker()

        with caplog.at_level(logging.WARNING, logger="story_video.utils.retry"):
            fn()

        # Should have logged for each retry (2 retries before success)
        retry_messages = [r for r in caplog.records if "Retrying" in r.message]
        assert len(retry_messages) == 2

    def test_no_log_on_first_success(self, caplog):
        """When the function succeeds on the first try, no retry logs appear."""

        @with_retry(retry_on=(Exception,), max_retries=3, base_delay=0.01)
        def fn():
            return "ok"

        with caplog.at_level(logging.WARNING, logger="story_video.utils.retry"):
            fn()

        retry_messages = [r for r in caplog.records if "Retrying" in r.message]
        assert len(retry_messages) == 0


# ---------------------------------------------------------------------------
# RetryError re-export
# ---------------------------------------------------------------------------


class TestRetryErrorReexport:
    """RetryError is re-exported from tenacity for consumer convenience."""

    def test_retry_error_is_same_as_tenacity(self):
        """Re-exported RetryError is the same class as tenacity.RetryError."""
        assert ReexportedRetryError is RetryError


# ---------------------------------------------------------------------------
# with_retry — function metadata
# ---------------------------------------------------------------------------


class TestWithRetryMetadata:
    """with_retry preserves function metadata."""

    def test_decorated_function_preserves_name(self):
        """The decorated function preserves the original function's __name__."""

        @with_retry(retry_on=(Exception,), max_retries=1, base_delay=0.01)
        def my_function():
            return 42

        assert my_function.__name__ == "my_function"


# ---------------------------------------------------------------------------
# _OPENAI_TRANSIENT — per-module constant (moved from retry.py in PR2-13)
# ---------------------------------------------------------------------------


class TestOpenAITransientPerModule:
    """Each OpenAI-consuming module defines its own _OPENAI_TRANSIENT tuple."""

    def test_tts_generator_defines_transient(self):
        """tts_generator has _OPENAI_TRANSIENT with the three OpenAI error types."""
        from openai import APIConnectionError, InternalServerError, RateLimitError

        from story_video.pipeline.tts_generator import _OPENAI_TRANSIENT

        assert isinstance(_OPENAI_TRANSIENT, tuple)
        assert len(_OPENAI_TRANSIENT) == 3
        assert APIConnectionError in _OPENAI_TRANSIENT
        assert RateLimitError in _OPENAI_TRANSIENT
        assert InternalServerError in _OPENAI_TRANSIENT

    def test_image_generator_defines_transient(self):
        """image_generator has _OPENAI_TRANSIENT with the three OpenAI error types."""
        from openai import APIConnectionError, InternalServerError, RateLimitError

        from story_video.pipeline.image_generator import _OPENAI_TRANSIENT

        assert isinstance(_OPENAI_TRANSIENT, tuple)
        assert len(_OPENAI_TRANSIENT) == 3
        assert APIConnectionError in _OPENAI_TRANSIENT
        assert RateLimitError in _OPENAI_TRANSIENT
        assert InternalServerError in _OPENAI_TRANSIENT

    def test_caption_generator_defines_transient(self):
        """caption_generator has _OPENAI_TRANSIENT with the three OpenAI error types."""
        from openai import APIConnectionError, InternalServerError, RateLimitError

        from story_video.pipeline.caption_generator import _OPENAI_TRANSIENT

        assert isinstance(_OPENAI_TRANSIENT, tuple)
        assert len(_OPENAI_TRANSIENT) == 3
        assert APIConnectionError in _OPENAI_TRANSIENT
        assert RateLimitError in _OPENAI_TRANSIENT
        assert InternalServerError in _OPENAI_TRANSIENT

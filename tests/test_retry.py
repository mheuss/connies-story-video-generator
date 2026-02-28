"""Tests for story_video.utils.retry — Retry decorators with tenacity."""

import logging

import openai
import pytest

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

    @pytest.mark.parametrize(
        "max_retries,fail_times,expected_calls",
        [
            (1, 100, 2),
            (5, 100, 6),
            (0, 1, 1),
        ],
        ids=["one_retry", "five_retries", "zero_no_retry"],
    )
    def test_custom_max_retries(self, max_retries, fail_times, expected_calls):
        """max_retries controls total attempt count."""
        tracker = TrackedCallable(fail_times=fail_times)

        @with_retry(retry_on=(RuntimeError,), max_retries=max_retries, base_delay=0.01)
        def fn():
            return tracker()

        with pytest.raises(RuntimeError):
            fn()
        assert tracker.call_count == expected_calls

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
# OPENAI_TRANSIENT — shared module verification
# ---------------------------------------------------------------------------


class TestOpenAITransient:
    """Shared OPENAI_TRANSIENT tuple contains the expected error types."""

    def test_openai_transient_contains_expected_errors(self):
        """Shared OPENAI_TRANSIENT tuple contains the 3 expected error types."""
        from story_video.utils.openai_compat import OPENAI_TRANSIENT

        assert isinstance(OPENAI_TRANSIENT, tuple)
        assert len(OPENAI_TRANSIENT) == 3
        assert openai.APIConnectionError in OPENAI_TRANSIENT
        assert openai.RateLimitError in OPENAI_TRANSIENT
        assert openai.InternalServerError in OPENAI_TRANSIENT

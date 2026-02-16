"""Retry decorators with exponential backoff using tenacity.

Provides thin wrappers around tenacity for retrying API calls (Claude, OpenAI TTS,
image generation, Whisper) with configurable exponential backoff. On failure, retries with
increasing delays capped at 60 seconds.

Usage:
    from story_video.utils.retry import with_retry, api_retry, RetryError

    @with_retry(max_retries=3, base_delay=2.0)
    def call_api():
        ...

    @api_retry
    def call_api_with_defaults():
        ...
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from openai import APIConnectionError, InternalServerError, RateLimitError
from tenacity import (
    RetryError,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

__all__ = ["OPENAI_TRANSIENT_ERRORS", "RetryError", "api_retry", "with_retry"]

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def with_retry(
    max_retries: int = 3,
    base_delay: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Create a retry decorator with exponential backoff.

    Wraps a function with tenacity retry logic. On failure, retries with
    exponential backoff (base_delay * 2^attempt). Logs each retry attempt
    at WARNING level.

    Args:
        max_retries: Maximum number of retry attempts after the initial call.
            Total attempts = max_retries + 1. For example, max_retries=3 means
            1 initial call + 3 retries = 4 total attempts.
        base_delay: Base delay in seconds for exponential backoff.
            Actual delay: base_delay * 2^(attempt-1), capped at 60 seconds.
        retry_on: Tuple of exception types to retry on.
            Defaults to (Exception,) which retries on any exception.

    Returns:
        A decorator that adds retry behavior to the wrapped function.

    Raises:
        The original exception when all retry attempts are exhausted.
            With reraise=True, the last exception raised by the wrapped
            function is re-raised directly, allowing callers to catch
            specific exception types (e.g., rate-limit vs auth errors).

    Example:
        @with_retry(max_retries=3, base_delay=2.0)
        def call_claude_api():
            ...

        @with_retry(max_retries=5, base_delay=1.0, retry_on=(ConnectionError, TimeoutError))
        def call_with_network_retry():
            ...
    """

    def decorator(func: F) -> F:
        decorated = retry(
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(multiplier=base_delay, max=60),
            retry=retry_if_exception_type(retry_on),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )(func)
        return decorated  # type: ignore[return-value]

    return decorator  # type: ignore[return-value]


def api_retry(func: F) -> F:
    """Convenience decorator using default retry settings.

    Equivalent to ``@with_retry(max_retries=3, base_delay=2.0)``.
    Use this for standard API calls that should use pipeline defaults.

    Args:
        func: The function to wrap with retry behavior.

    Returns:
        The wrapped function with default retry settings applied.

    Example:
        @api_retry
        def call_openai_tts():
            ...
    """
    return with_retry()(func)


# Shared transient error tuple for OpenAI API calls.
# Used by tts_generator, image_generator, and caption_generator.
OPENAI_TRANSIENT_ERRORS = (APIConnectionError, RateLimitError, InternalServerError)

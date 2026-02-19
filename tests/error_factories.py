"""Shared error factories for API retry tests.

Eliminates duplicated OpenAI error construction boilerplate across
TTS, image, and caption test files.
"""

from unittest.mock import MagicMock


def make_openai_rate_limit_error():
    """Build an OpenAI RateLimitError with a mock 429 response."""
    from openai import RateLimitError

    response = MagicMock()
    response.status_code = 429
    response.json.return_value = {"error": {"message": "rate limited"}}
    return RateLimitError(
        message="rate limited",
        response=response,
        body={"error": {"message": "rate limited"}},
    )


def make_openai_server_error():
    """Build an OpenAI InternalServerError with a mock 500 response."""
    from openai import InternalServerError

    response = MagicMock()
    response.status_code = 500
    response.json.return_value = {"error": {"message": "server error"}}
    return InternalServerError(
        message="server error",
        response=response,
        body={"error": {"message": "server error"}},
    )


def make_openai_connection_error():
    """Build an OpenAI APIConnectionError with a mock request."""
    from openai import APIConnectionError

    return APIConnectionError(request=MagicMock())

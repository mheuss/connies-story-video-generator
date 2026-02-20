"""Tests for story_video.pipeline.claude_client — Claude API wrapper.

TDD: These tests are written first, before the implementation.
Each test verifies one logical behavior of the ClaudeClient wrapper.
"""

from unittest.mock import MagicMock

import pytest

from story_video.pipeline.claude_client import ClaudeClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text_response(text: str) -> MagicMock:
    """Build a mock Messages.create response containing a single text block."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    response = MagicMock()
    response.content = [text_block]
    return response


def _make_tool_use_response(tool_name: str, tool_input: dict) -> MagicMock:
    """Build a mock Messages.create response containing a tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = tool_name
    tool_block.input = tool_input

    response = MagicMock()
    response.content = [tool_block]
    return response


def _make_text_only_response_no_tool() -> MagicMock:
    """Build a mock response that contains only a text block (no tool_use)."""
    return _make_text_response("Some text but no tool usage.")


@pytest.fixture()
def mock_anthropic(monkeypatch):
    """Patch anthropic.Anthropic to return a mock client."""
    mock_client = MagicMock()
    mock_class = MagicMock(return_value=mock_client)
    monkeypatch.setattr("story_video.pipeline.claude_client.anthropic.Anthropic", mock_class)
    return mock_client


@pytest.fixture()
def mock_anthropic_class(monkeypatch):
    """Patch anthropic.Anthropic and return the class mock (not the instance).

    Useful for verifying how Anthropic() was constructed.
    """
    mock_client = MagicMock()
    mock_class = MagicMock(return_value=mock_client)
    monkeypatch.setattr("story_video.pipeline.claude_client.anthropic.Anthropic", mock_class)
    return mock_class


# ---------------------------------------------------------------------------
# generate — text extraction
# ---------------------------------------------------------------------------


class TestGenerateReturnsText:
    """generate() extracts text from the SDK response."""

    def test_generate_returns_text(self, mock_anthropic):
        """generate() returns the text from the first text block."""
        mock_anthropic.messages.create.return_value = _make_text_response("Once upon a time...")

        client = ClaudeClient()
        result = client.generate(system="You are a writer.", user_message="Tell a story.")

        assert result == "Once upon a time..."

    def test_generate_no_text_block_raises(self, mock_anthropic):
        """generate() raises ValueError when response has no text block."""
        response = MagicMock()
        response.content = []
        mock_anthropic.messages.create.return_value = response

        client = ClaudeClient()

        with pytest.raises(ValueError, match="No text block in response"):
            client.generate(system="sys", user_message="msg")


# ---------------------------------------------------------------------------
# generate — message format
# ---------------------------------------------------------------------------


class TestGenerateMessageFormat:
    """generate() sends correctly formatted messages to the SDK."""

    def test_generate_passes_system_and_user_message(self, mock_anthropic):
        """generate() passes system prompt and user message to the SDK."""
        mock_anthropic.messages.create.return_value = _make_text_response("ok")

        client = ClaudeClient()
        client.generate(system="Be helpful.", user_message="Hello.")

        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "Be helpful."
        assert call_kwargs["messages"] == [{"role": "user", "content": "Hello."}]

    def test_generate_passes_model_and_max_tokens(self, mock_anthropic):
        """generate() forwards model and max_tokens to the SDK."""
        mock_anthropic.messages.create.return_value = _make_text_response("ok")

        client = ClaudeClient()
        client.generate(system="sys", user_message="msg", max_tokens=2048)

        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-5-20250929"
        assert call_kwargs["max_tokens"] == 2048

    def test_generate_custom_model(self, mock_anthropic):
        """ClaudeClient with a custom model passes that model to the SDK."""
        mock_anthropic.messages.create.return_value = _make_text_response("ok")

        client = ClaudeClient(model="claude-opus-4-20250514")
        client.generate(system="sys", user_message="msg")

        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-20250514"


# ---------------------------------------------------------------------------
# generate_structured — tool_use extraction
# ---------------------------------------------------------------------------


class TestGenerateStructuredReturnsToolInput:
    """generate_structured() extracts tool input from the SDK response."""

    def test_generate_structured_returns_tool_input(self, mock_anthropic):
        """generate_structured() returns the parsed tool input dict."""
        expected = {"title": "My Story", "scenes": 5}
        mock_anthropic.messages.create.return_value = _make_tool_use_response(
            "story_splitter", expected
        )

        client = ClaudeClient()
        result = client.generate_structured(
            system="Split the story.",
            user_message="Here is a story...",
            tool_name="story_splitter",
            tool_schema={"type": "object", "properties": {}},
        )

        assert result == expected


# ---------------------------------------------------------------------------
# generate_structured — tool_choice and tool definition
# ---------------------------------------------------------------------------


class TestGenerateStructuredToolConfig:
    """generate_structured() sends correct tool configuration to the SDK."""

    def test_generate_structured_forces_tool_choice(self, mock_anthropic):
        """generate_structured() forces tool_choice to the specified tool."""
        mock_anthropic.messages.create.return_value = _make_tool_use_response("my_tool", {})

        client = ClaudeClient()
        client.generate_structured(
            system="sys",
            user_message="msg",
            tool_name="my_tool",
            tool_schema={"type": "object"},
        )

        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "my_tool"}

    def test_generate_structured_passes_tool_definition(self, mock_anthropic):
        """generate_structured() passes the tool definition with correct schema."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        mock_anthropic.messages.create.return_value = _make_tool_use_response(
            "extractor", {"name": "test"}
        )

        client = ClaudeClient()
        client.generate_structured(
            system="sys",
            user_message="msg",
            tool_name="extractor",
            tool_schema=schema,
        )

        call_kwargs = mock_anthropic.messages.create.call_args.kwargs
        tools = call_kwargs["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "extractor"
        assert tools[0]["description"] == "Structured output tool"
        assert tools[0]["input_schema"] == schema


# ---------------------------------------------------------------------------
# generate_structured — missing tool_use block
# ---------------------------------------------------------------------------


class TestGenerateStructuredNoToolUseBlock:
    """generate_structured() raises ValueError when no tool_use block is found."""

    def test_generate_structured_no_tool_use_block_raises(self, mock_anthropic):
        """ValueError is raised when the response has no tool_use block."""
        mock_anthropic.messages.create.return_value = _make_text_only_response_no_tool()

        client = ClaudeClient()

        with pytest.raises(ValueError, match="No tool_use block in response"):
            client.generate_structured(
                system="sys",
                user_message="msg",
                tool_name="missing_tool",
                tool_schema={"type": "object"},
            )


# ---------------------------------------------------------------------------
# Retry behavior — transient errors
# ---------------------------------------------------------------------------


class TestRetryOnTransientErrors:
    """Both methods retry on transient API errors (connection, rate-limit, server)."""

    def test_generate_retries_on_connection_error(self, mock_anthropic):
        """generate() retries on APIConnectionError then succeeds."""
        from anthropic import APIConnectionError

        mock_anthropic.messages.create.side_effect = [
            APIConnectionError(request=MagicMock()),
            _make_text_response("recovered"),
        ]

        client = ClaudeClient()
        result = client.generate(system="sys", user_message="msg")

        assert result == "recovered"
        assert mock_anthropic.messages.create.call_count == 2

    def test_generate_retries_on_rate_limit(self, mock_anthropic):
        """generate() retries on RateLimitError then succeeds."""
        from anthropic import RateLimitError

        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.json.return_value = {"error": {"message": "rate limited"}}

        mock_anthropic.messages.create.side_effect = [
            RateLimitError(
                message="rate limited",
                response=response_429,
                body={"error": {"message": "rate limited"}},
            ),
            _make_text_response("recovered"),
        ]

        client = ClaudeClient()
        result = client.generate(system="sys", user_message="msg")

        assert result == "recovered"
        assert mock_anthropic.messages.create.call_count == 2

    def test_generate_retries_on_server_error(self, mock_anthropic):
        """generate() retries on InternalServerError then succeeds."""
        from anthropic import InternalServerError

        response_500 = MagicMock()
        response_500.status_code = 500
        response_500.json.return_value = {"error": {"message": "server error"}}

        mock_anthropic.messages.create.side_effect = [
            InternalServerError(
                message="server error",
                response=response_500,
                body={"error": {"message": "server error"}},
            ),
            _make_text_response("recovered"),
        ]

        client = ClaudeClient()
        result = client.generate(system="sys", user_message="msg")

        assert result == "recovered"
        assert mock_anthropic.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Retry behavior — permanent errors
# ---------------------------------------------------------------------------


class TestNoRetryOnPermanentErrors:
    """Both methods do NOT retry on permanent API errors."""

    def test_generate_no_retry_on_auth_error(self, mock_anthropic):
        """generate() does not retry on AuthenticationError."""
        from anthropic import AuthenticationError

        response_401 = MagicMock()
        response_401.status_code = 401
        response_401.json.return_value = {"error": {"message": "invalid key"}}

        mock_anthropic.messages.create.side_effect = AuthenticationError(
            message="invalid key",
            response=response_401,
            body={"error": {"message": "invalid key"}},
        )

        client = ClaudeClient()

        with pytest.raises(AuthenticationError):
            client.generate(system="sys", user_message="msg")

        assert mock_anthropic.messages.create.call_count == 1

    def test_generate_no_retry_on_bad_request(self, mock_anthropic):
        """generate() does not retry on BadRequestError."""
        from anthropic import BadRequestError

        response_400 = MagicMock()
        response_400.status_code = 400
        response_400.json.return_value = {"error": {"message": "bad request"}}

        mock_anthropic.messages.create.side_effect = BadRequestError(
            message="bad request",
            response=response_400,
            body={"error": {"message": "bad request"}},
        )

        client = ClaudeClient()

        with pytest.raises(BadRequestError):
            client.generate(system="sys", user_message="msg")

        assert mock_anthropic.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# Retry behavior — structured methods
# ---------------------------------------------------------------------------


class TestRetryOnStructuredMethods:
    """generate_structured() has the same retry behavior as generate()."""

    def test_generate_structured_retries_on_transient_error(self, mock_anthropic):
        """generate_structured() retries on transient errors then succeeds."""
        from anthropic import APIConnectionError

        expected = {"result": "ok"}
        mock_anthropic.messages.create.side_effect = [
            APIConnectionError(request=MagicMock()),
            _make_tool_use_response("my_tool", expected),
        ]

        client = ClaudeClient()
        result = client.generate_structured(
            system="sys",
            user_message="msg",
            tool_name="my_tool",
            tool_schema={"type": "object"},
        )

        assert result == expected
        assert mock_anthropic.messages.create.call_count == 2

    def test_generate_structured_no_retry_on_permanent_error(self, mock_anthropic):
        """generate_structured() does not retry on permanent errors."""
        from anthropic import AuthenticationError

        response_401 = MagicMock()
        response_401.status_code = 401
        response_401.json.return_value = {"error": {"message": "invalid key"}}

        mock_anthropic.messages.create.side_effect = AuthenticationError(
            message="invalid key",
            response=response_401,
            body={"error": {"message": "invalid key"}},
        )

        client = ClaudeClient()

        with pytest.raises(AuthenticationError):
            client.generate_structured(
                system="sys",
                user_message="msg",
                tool_name="my_tool",
                tool_schema={"type": "object"},
            )

        assert mock_anthropic.messages.create.call_count == 1


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------


class TestDefaultConfiguration:
    """ClaudeClient default configuration is correct."""

    def test_client_reads_api_key_from_env(self, mock_anthropic_class):
        """Anthropic() is called without explicit API key (reads from env)."""
        _ = ClaudeClient()

        mock_anthropic_class.assert_called_once_with()


# ---------------------------------------------------------------------------
# Retry exhaustion — all retries consumed
# ---------------------------------------------------------------------------


class TestRetryExhaustion:
    """When all retries are exhausted, the original exception is re-raised."""

    def test_generate_raises_after_all_retries_exhausted(self, mock_anthropic):
        """4 consecutive transient errors (1 initial + 3 retries) re-raises the original error."""
        from anthropic import APIConnectionError

        error = APIConnectionError(request=MagicMock())
        mock_anthropic.messages.create.side_effect = [error, error, error, error]

        client = ClaudeClient()

        with pytest.raises(APIConnectionError):
            client.generate(system="sys", user_message="msg")

        # max_retries=3 → 1 initial + 3 retries = 4 total attempts
        assert mock_anthropic.messages.create.call_count == 4

    def test_generate_structured_raises_after_all_retries_exhausted(self, mock_anthropic):
        """4 consecutive transient errors on generate_structured re-raises the original error."""
        from anthropic import InternalServerError

        response_500 = MagicMock()
        response_500.status_code = 500
        response_500.json.return_value = {"error": {"message": "server error"}}

        error = InternalServerError(
            message="server error",
            response=response_500,
            body={"error": {"message": "server error"}},
        )
        mock_anthropic.messages.create.side_effect = [error, error, error, error]

        client = ClaudeClient()

        with pytest.raises(InternalServerError):
            client.generate_structured(
                system="sys",
                user_message="msg",
                tool_name="my_tool",
                tool_schema={"type": "object"},
            )

        assert mock_anthropic.messages.create.call_count == 4

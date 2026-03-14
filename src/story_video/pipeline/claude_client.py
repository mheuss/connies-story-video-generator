"""Thin wrapper around the Anthropic Python SDK.

Provides two methods for Claude API calls: free-text generation and structured
output via tool_use. Handles retries on transient API errors. The client is a
"dumb pipe" — it handles transport and retries, not prompts.

Usage:
    from story_video.pipeline.claude_client import ClaudeClient

    client = ClaudeClient()
    text = client.generate(system="You are a writer.", user_message="Tell a story.")
    data = client.generate_structured(
        system="Extract data.",
        user_message="...",
        tool_name="extractor",
        tool_schema={"type": "object", "properties": {"name": {"type": "string"}}},
    )
"""

import anthropic
from anthropic import APIConnectionError, InternalServerError, RateLimitError

from story_video.utils.retry import with_retry

__all__ = ["ClaudeClient"]

TRANSIENT_ERRORS = (APIConnectionError, RateLimitError, InternalServerError)


class ClaudeClient:
    """Thin wrapper around the Anthropic Python SDK.

    Provides two methods for Claude API calls: free-text generation and
    structured output via tool_use. Handles retries on transient API errors.

    Args:
        model: Claude model identifier. Defaults to claude-sonnet-4-5-20250929.
            This default is hardcoded rather than derived from config because
            ClaudeClient is instantiated before AppConfig is loaded in several
            code paths. Update this value when upgrading the model.
    """

    def __init__(self, model: str = "claude-sonnet-4-5-20250929"):
        self._client = anthropic.Anthropic()  # Reads ANTHROPIC_API_KEY from env
        self._model = model

    @with_retry(max_retries=3, base_delay=2.0, retry_on=TRANSIENT_ERRORS)
    def generate(self, system: str, user_message: str, max_tokens: int = 4096) -> str:
        """Simple text generation. Returns response text.

        Sends a single user message with a system prompt to Claude and returns
        the text content of the first response block.

        Args:
            system: System prompt providing context and instructions.
            user_message: The user message to send.
            max_tokens: Maximum number of tokens in the response.

        Returns:
            The text content from the first text block in the response.

        Raises:
            ValueError: If the response contains no text block.
        """
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )

        for block in response.content:
            if block.type == "text":
                return block.text

        raise ValueError("No text block in response")

    @with_retry(max_retries=3, base_delay=2.0, retry_on=TRANSIENT_ERRORS)
    def generate_structured(
        self,
        system: str,
        user_message: str,
        tool_name: str,
        tool_schema: dict,
        max_tokens: int = 8192,
    ) -> dict:
        """Tool_use generation. Returns parsed tool input dict.

        Forces Claude to use the specified tool via tool_choice, then extracts
        and returns the tool input as a parsed dict.

        Args:
            system: System prompt providing context and instructions.
            user_message: The user message to send.
            tool_name: Name of the tool to force Claude to use.
            tool_schema: JSON Schema defining the tool's input structure.
            max_tokens: Maximum number of tokens in the response.

        Returns:
            The parsed tool input dictionary from the tool_use block.

        Raises:
            ValueError: If the response contains no tool_use block.
        """
        tool_def = {
            "name": tool_name,
            "description": "Structured output tool",
            "input_schema": tool_schema,
        }

        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=[tool_def],
            tool_choice={"type": "tool", "name": tool_name},
        )

        for block in response.content:
            if block.type == "tool_use":
                return block.input

        raise ValueError("No tool_use block in response")

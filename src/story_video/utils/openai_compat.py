"""Shared OpenAI SDK compatibility constants."""

import openai

OPENAI_TRANSIENT = (
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)

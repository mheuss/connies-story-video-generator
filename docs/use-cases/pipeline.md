# Pipeline Use-Cases

## Claude API Structured Output via Tool Use

**Problem:** Need Claude to return structured JSON matching a specific schema, not free-form text.

**Problem indicators:**
- "need structured output from Claude"
- "how do I get JSON from Claude API"
- "force Claude to return a specific schema"
- "tool_use for structured data extraction"

**Location:** `src/story_video/pipeline/claude_client.py:ClaudeClient.generate_structured`

**Notes:** Uses Claude's tool_use mechanism with `tool_choice={"type": "tool", "name": ...}` to force structured output, not actual tool calling. The tool definition's `input_schema` acts as the output schema. The SDK returns `block.input` as a parsed Python dict, so no JSON parsing is needed. This is the recommended approach over asking Claude to output JSON in a text response, because the schema is enforced by the API.

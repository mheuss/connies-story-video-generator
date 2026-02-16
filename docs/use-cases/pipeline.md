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

## Provider Abstraction for External API Calls

**Problem:** Need to call external APIs (OpenAI TTS, GPT Image, Whisper) with retry logic while keeping the public pipeline function testable and provider-swappable.

**Problem indicators:**
- "how to abstract an external API provider"
- "need to swap API providers without changing pipeline logic"
- "testing pipeline functions without real API calls"
- "Protocol vs ABC for provider interfaces"

**Location:** `src/story_video/pipeline/tts_generator.py:TTSProvider` (pattern repeated in `image_generator.py:ImageProvider`, `caption_generator.py:CaptionProvider`)

**Notes:** Uses `typing.Protocol` (structural subtyping) instead of ABC — no registration, no inheritance required. The `@with_retry` decorator lives on the provider's API method, not the public function, so retry logic travels with the provider. The public function takes `(scene, state, provider)` and handles file I/O + state updates. This separation means tests mock at the provider level (returning canned bytes/data), not the SDK level. The orchestrator instantiates the concrete provider and passes it in — no factory, no DI container.

## Whisper Punctuation Reconciliation

**Problem:** Whisper word-level timestamps strip punctuation but segment text preserves it. Need to restore punctuation to words for accurate subtitle rendering.

**Problem indicators:**
- "Whisper words have no punctuation"
- "how to get punctuation in word timestamps"
- "caption words missing periods and commas"
- "reconcile segment text with word timestamps"

**Location:** `src/story_video/pipeline/caption_generator.py:_reconcile_punctuation`

**Notes:** Walks each segment's text with a cursor, matching words by time range and position. After matching a word, grabs trailing non-alphanumeric, non-space characters as punctuation. Fails gracefully — unmatched words (e.g. Whisper hallucination, different capitalization) are left unchanged. Case-insensitive fallback for matching. Returns a new CaptionResult (immutable). Called automatically inside `generate_captions()` before JSON serialization — no caller action required.

## Sequential Phase Orchestration with Resume

**Problem:** Need to run multiple pipeline phases in order, with the ability to pause for human review, resume from any state (fresh, failed, in-progress, awaiting review), and skip already-completed work.

**Problem indicators:**
- "how to sequence pipeline phases with checkpoints"
- "resume a multi-phase pipeline from where it stopped"
- "skip completed scenes on retry"
- "pause pipeline for human review then continue"

**Location:** `src/story_video/pipeline/orchestrator.py:run_pipeline`

**Notes:** Single `run_pipeline()` function drives all phases. Resume logic in `_determine_start_phase()` inspects `current_phase` and `status` to decide where to start. Checkpoint phases call `await_review()` instead of `complete_phase()` in semi-auto mode, then return — caller resumes by calling `run_pipeline()` again. Per-scene phases use `get_scenes_for_processing()` to skip completed scenes automatically. State is saved at three points: checkpoint pause, phase failure, and end of full run. Tests mock all pipeline modules via `@patch` — no real API calls.

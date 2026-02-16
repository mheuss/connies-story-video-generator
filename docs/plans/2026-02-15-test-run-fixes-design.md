# Test Run Fixes Design

## Scope

Fix four issues discovered during the first end-to-end test run of the adapt flow.

## Issues

### 1. Jerky Ken Burns Motion

**Problem:** The zoompan filter in `filters.py` uses linear interpolation for position and zoom. This causes jerky motion from two sources: integer pixel snapping (zoompan truncates fractional positions) and no easing (linear motion looks mechanical).

**Fix:** Replace linear `on/{frames}` expressions with sine-based ease-in-out: `(1-cos(on/{frames}*PI))/2`. This produces smooth start/stop cinematic drift. Add `ken_burns_enabled` boolean to `VideoConfig` (default `true`) so the effect can be disabled, falling back to a still image with blurred background.

**Files:**
- `ffmpeg/filters.py` — replace linear expressions with eased expressions
- `models.py` — add `VideoConfig.ken_burns_enabled: bool = True`
- `pipeline/video_assembler.py` — check config before applying Ken Burns filter

### 2. Missing Caption Punctuation

**Problem:** Whisper word-level timestamps strip punctuation ("west" instead of "west."), but segment text preserves it. Our subtitle generator uses word timestamps, so rendered captions show bare text.

**Fix:** Add `_reconcile_punctuation(result: CaptionResult) -> CaptionResult` post-processing in `caption_generator.py`. For each word, find its parent segment by time range, locate the word in segment text, and append any trailing punctuation. Runs before JSON serialization. Fails gracefully — leaves unmatched words unchanged.

**Algorithm:**
1. For each segment, track a cursor position in segment text
2. For each word within the segment's time range, find it at cursor position
3. After word match, grab trailing non-alphanumeric characters (punctuation)
4. Append punctuation to `word.word`

**Files:**
- `pipeline/caption_generator.py` — add `_reconcile_punctuation()`, call before saving JSON

### 3. Short Story Scene Count

**Problem:** The scene split prompt targets 1500-2000 words per scene. A 220-word test story produced only 1 scene — a 75-second video with a single static image. Additionally, the image prompt writer hallucinated prompts for scenes 2-4 that didn't exist.

**Fix:** Add short-story guidance to `SCENE_SPLIT_SYSTEM`: "For stories under 1000 words, create at least 2 scenes at the strongest narrative shift." Update `IMAGE_PROMPT_SYSTEM` to explicitly reference the provided scene numbers, reducing hallucinated extras.

**Files:**
- `pipeline/story_writer.py` — update `SCENE_SPLIT_SYSTEM` prompt
- `pipeline/image_prompt_writer.py` — update `IMAGE_PROMPT_SYSTEM` prompt

### 4. Wrong Success Message Path

**Problem:** `_display_outcome` says "Video files are in: .../video" but the final video is `final.mp4` in the project root. The `video/` subdirectory is empty.

**Fix:** Change success message to point to `project_dir / "final.mp4"`.

**Files:**
- `cli.py` — update success panel in `_display_outcome`

## Testing

| Issue | Testing approach |
|-------|-----------------|
| Ken Burns | Update `test_filters.py` — verify eased expressions, test config toggle in assembler |
| Punctuation | New tests in `test_caption_generator.py` — verify recovery from segments to words |
| Scene count | Prompt text change — validated by next end-to-end run |
| Success path | Update `test_cli.py` — verify message contains `final.mp4` |

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Easing curve | Sine (ease-in-out) | Standard cinematic motion, single formula |
| Ken Burns fallback | Config toggle | Clean disable path, no code branching needed |
| Punctuation source | Segment text | Already has punctuation, words provide timing |
| Reconciliation failure | Graceful degradation | Leave word unchanged if match fails |
| Scene minimum | Prompt guidance | No config complexity, Claude handles the judgment |
| Image prompt constraint | Prompt text | Schema validation is overkill for this |

## Out of Scope

- Pillow-based frame rendering (zoompan easing should be sufficient)
- Schema changes to constrain scene numbers
- Changes to subtitle rendering logic (fix is at the data layer)
- `video/` directory removal from project scaffold

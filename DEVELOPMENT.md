# Development

## Architectural Decision Records

Significant technical decisions with context and rationale.

### ADR-001: Multi-Phase Pipeline Architecture

**Status:** Accepted

**Context:** Story video generation involves many sequential steps (writing, TTS, image generation, captioning, video assembly). Each step depends on the previous one's output and can fail independently.

**Decision:** Implement a multi-phase pipeline with per-phase state tracking. Each phase saves its output to disk and updates project.json status. The pipeline can pause between phases for human review (semi-automated mode) or run continuously (autonomous mode).

**Consequences:**
- Enables resume after failure — only re-run from the failed phase
- Allows human review at critical checkpoints (especially outline phase)
- Adds complexity in state management (project.json tracking)
- Per-scene granularity allows partial re-generation

---

### ADR-002: Three Input Modes with Shared Downstream Phases

**Status:** Accepted

**Context:** Users want to generate videos from scratch (original), adapt existing stories (adapt), or create new stories inspired by existing ones (inspired_by). These modes differ in creative phases but share media generation.

**Decision:** Split the pipeline into mode-specific creative flows (Phases 1-5 for original/inspired_by, Phases 1-3 for adapt) that converge at image prompt generation. Downstream phases (TTS, images, captions, video) are identical across modes.

**Consequences:**
- Code reuse for media generation phases
- Mode-specific logic is isolated in story_writer.py
- The script.json format must accommodate output from all three modes
- Testing requires covering all three input paths

---

### ADR-003: OpenAI as Primary TTS Provider

**Status:** Superseded by ADR-007

**Context:** Need consistent, affordable narration for 30-120 minute videos. ElevenLabs offers more expressive voices but costs 7-14x more ($22-48 vs $3.24 for 2 hours).

**Decision:** Use OpenAI gpt-4o-mini-tts as the default provider. ElevenLabs is now available as an alternative via `tts.provider: elevenlabs` in config. Both providers implement the `TTSProvider` Protocol with optional `instructions` for emotion direction.

**Consequences:**
- Cost-effective for long-form content
- Clean, consistent voice quality with emotion direction via instructions
- Provider abstraction via Protocol enables both OpenAI and ElevenLabs
- ElevenLabs available for projects that need more expressive voices

---

### ADR-004: Craft Notes as Style Consistency Anchor

**Status:** Accepted

**Context:** When generating a multi-scene story across many API calls, voice and style can drift. Each scene is generated in a separate Claude call with limited context.

**Decision:** Phase 1 analyzes the style reference to produce explicit "craft notes" — concrete rules about sentence structure, vocabulary, tone, and pacing. These notes are included in every subsequent generation call as a consistency anchor.

**Consequences:**
- Prevents voice drift across 25+ separate API calls
- Adds ~500-1000 tokens to every scene generation context
- Quality of craft notes directly impacts story consistency
- Works for all three modes. Adapt mode uses a lighter analysis prompt focused on visual illustration rather than craft emulation

---

### ADR-005: Per-Scene Video Segment Assembly

**Status:** Accepted

**Context:** FFmpeg video assembly for a 30-minute video with 25 scenes is complex. A single monolithic FFmpeg command would be fragile and impossible to debug or resume.

**Decision:** Render each scene as an independent video segment (segment_01.mp4, segment_02.mp4, etc.), then concatenate with crossfade transitions in a final pass.

**Consequences:**
- Failed scenes only require re-rendering that segment
- Natural resume capability — skip already-rendered segments
- Slightly larger intermediate storage (individual segments + final)
- Crossfade transitions applied during concatenation, not per-segment

---

### ADR-006: Narration Prep as Separate Phase

**Status:** Accepted

**Context:** TTS engines struggle with abbreviations, numbers, and certain punctuation. Raw prose needs transformation for optimal speech output.

**Decision:** Add a dedicated narration prep phase after prose finalization. This produces a parallel `narration_text` field per scene while preserving the original prose. A single Claude API call per scene handles abbreviation expansion, number pronunciation, punctuation smoothing, and contextual decisions. Voice/mood tags are validated after each call (retry once on corruption, then fail). A pronunciation guide accumulates across scenes.

**Consequences:**
- Original prose preserved for display/review
- TTS receives optimized text for better audio quality
- Adds a processing step between writing and audio generation
- Context-aware decisions (e.g., "Dr." as "Doctor" vs "Drive") handled by LLM
- Produces a JSON changelog of all modifications for review

---

### ADR-007: Multi-Voice TTS with Inline Tags

**Status:** Accepted

**Context:** Stories with dialogue need different voices for different characters and emotion direction for dramatic effect. The system must support multiple TTS voices per scene while remaining backward compatible with single-voice stories.

**Decision:** Use YAML front matter in the story text to define voice label-to-provider-ID mappings, and inline markdown-bold tags (`**voice:X**`, `**mood:X**`) to switch voice and emotion mid-text. A tag parser splits narration text into `NarrationSegment` objects, each with its own voice and mood. The TTS generator calls `provider.synthesize()` once per segment and concatenates the resulting audio bytes. The `TTSProvider` Protocol gains an optional `instructions` parameter for emotion direction. OpenAI maps this to its native `instructions` field; ElevenLabs translates it to audio tags (`[sorrowful]`, `[excited]`, etc.) prepended to the text.

**Consequences:**
- Stories without headers work identically to before (backward compatible)
- Each provider maps mood instructions to its native mechanism (no lowest-common-denominator)
- MP3/opus byte concatenation works because frames are independently decodable; WAV/FLAC would need FFmpeg concat (deferred)
- Voice tags reset mood state to avoid stale emotion carrying across characters
- The `instructions` parameter is a breaking change for custom `TTSProvider` implementations

---

### ADR-008: File-Based Artifact Storage for Creative Phases

**Status:** Accepted

**Context:** The inspired_by creative flow produces intermediate artifacts (analysis, story bible, outline) that subsequent phases read. These could be stored in `ProjectMetadata` (Pydantic model) or as JSON files on disk.

**Decision:** Store creative phase artifacts as JSON files (`analysis.json`, `story_bible.json`, `outline.json`) in the project directory, not in `ProjectMetadata`. Scene prose goes into `state.metadata.scenes` via `add_scene()` (existing pattern).

**Consequences:**
- Human-readable at checkpoint pauses — users can review and edit before continuing
- No model changes needed — `ProjectMetadata` stays focused on pipeline state
- Consistent with existing patterns (scene `.md` files, `narration_flags.md`)
- Each phase reads its dependencies from disk, making the data flow explicit
- Resume works naturally — if a file exists, the phase already ran

---

### ADR-009: Inline Image Tags for Multi-Image Scenes

**Status:** Accepted

**Context:** Authors want to control when images change within a scene, independent of scene boundaries. A single image per scene is limiting for longer scenes or scenes that span multiple visual contexts.

**Decision:** Authors define image prompts in a YAML front matter `images:` map and place `**image:tag**` tags inline in scene text. Tag parsing extracts character offsets. During caption generation, Whisper word-level timestamps map character positions to audio time. Each image gets a computed `(start, end)` timing based on where its tag appears in the narration. FFmpeg renders multi-image scenes with per-image blur+foreground composites chained through xfade crossfade transitions. A minimum display duration (4.0s + crossfade duration) is enforced at assembly time as a hard error.

**Consequences:**
- Authors control image transitions at any point in the narration, not just scene boundaries
- Scenes without image tags work identically to before (backward compatible)
- YAML-defined prompts skip Claude during IMAGE_PROMPTS phase (cost savings for tagged scenes)
- Image timing depends on Whisper caption accuracy — poor transcription could misplace transitions
- Minimum display duration validation prevents images from flashing too briefly
- Multi-image filter graph adds FFmpeg complexity (N inputs, N-1 xfade chains)

---

### ADR-010: Background Music via Inline Tags and FFmpeg amix

**Status:** Accepted

**Context:** Authors want to layer background music and sound effects onto narration at specific points in the story. Music files are supplied by the user, not generated. The system already has inline tag infrastructure from image tags (ADR-009) and voice/mood tags (ADR-007).

**Decision:** Reuse the inline tag pattern: authors define audio assets in a YAML front matter `audio:` map (with `file`, `volume`, `loop`, `fade_in`, `fade_out` properties) and place `**music:key**` tags in scene text. Tag parsing computes character offsets in stripped-text coordinates. During video assembly, character positions are mapped to Whisper timestamps via `bisect_left` on cumulative word offsets (same approach as image timing). FFmpeg mixes narration with music tracks using per-track filter chains (`adelay` for start offset, `volume` for level, `aloop`+`atrim` for looping, `afade` for fades) fed into `amix`. Music scope is per-scene only — tracks do not carry across scene boundaries.

**Consequences:**
- Consistent authoring model — same YAML + inline tag pattern as images and voice/mood
- Per-scene scope simplifies implementation (no cross-segment state) at the cost of continuous background music
- Audio file paths resolved relative to project directory (where `source_story.txt` lives)
- `assemble_scene` re-parses the story header when audio cues are present (simple, avoids new artifact files)
- The `amix` filter uses `duration=first` so output matches narration length regardless of music track length
- Looping with `aloop` enables short sound files to fill long scenes

---

## Technical Notes

### Patterns

- **Provider abstraction:** TTS and image generation use `typing.Protocol` (structural subtyping) for provider interfaces. Each provider implements a `synthesize` / `generate` method. Concrete TTS providers: `OpenAITTSProvider`, `ElevenLabsTTSProvider`. Retry logic lives on the provider method via `@with_retry`, not the public function.
- **State tracking via project.json:** All phase and scene statuses tracked in a single JSON file. Statuses follow: pending -> in_progress -> completed/awaiting_review/failed.
- **Running summaries for context management:** Long stories use compressed summaries of prior events to stay within context limits. Each scene generation receives: style reference, craft notes, story bible, outline, previous scene, running summary, and scene beat.

### Gotchas

- Image generation models have no cross-image memory — each image prompt must be fully self-contained with character descriptions
- GPT Image 1.5 uses different API parameters than DALL-E 3 — `output_format` (png/webp/jpeg) instead of `response_format` (b64_json/url), no `style` parameter, different size options (1024x1024, 1024x1536, 1536x1024, auto). The image generator detects model type via `model.startswith("gpt-image")` to branch parameter construction.
- OpenAI TTS has a character limit per request — long scenes may need chunking
- Multi-voice TTS concatenates raw MP3 bytes from multiple `synthesize()` calls. This works because MP3 frames are independently decodable. WAV/FLAC would need FFmpeg concat instead. A format guard in `generate_audio` raises `ValueError` if multi-segment mode is used with a format whose prefix is not in `_CONCAT_SAFE_PREFIXES` (mp3, opus).
- ElevenLabs does not support the `speed` parameter — a warning is logged if speed != 1.0
- ElevenLabs mood mapping uses `_mood_to_elevenlabs_text()` which receives the raw mood keyword directly via the `mood` parameter and wraps it as a freeform audio tag (e.g., `[excited]`) prepended to text.
- FFmpeg filter complexity grows with video effects — blur background + still image overlay + subtitle rendering requires careful filter graph construction
- **Tag coordinate systems:** Inline tags (`**image:X**`, `**music:X**`, `**voice:X**`, `**mood:X**`) exist in raw prose but are stripped before TTS. Any feature that maps tag positions to Whisper timestamps must compute positions in the *stripped-text* coordinate system, not raw prose. The pipeline strips tags at different stages (image tags in `_populate_image_tags`, music tags in `_populate_music_tags`, voice/mood tags in `parse_narration_segments`), so positions must account for all preceding tag characters. See `extract_image_tags_stripped()` and `extract_music_tags_stripped()` in `narration_tags.py`.

### External Integrations

- **Anthropic Claude API** — Story generation (all creative phases). Uses anthropic Python SDK.
- **OpenAI API** — TTS (gpt-4o-mini-tts model with emotion instructions), image generation (GPT Image 1.5 and DALL-E 3), caption timing (Whisper). Uses openai Python SDK.
- **ElevenLabs API** — Alternative TTS provider with audio tag emotion control. Uses elevenlabs Python SDK. Selected via `tts.provider: elevenlabs` in config.
- **FFmpeg** — Video assembly, filters, transitions, subtitle rendering. Called as subprocess.

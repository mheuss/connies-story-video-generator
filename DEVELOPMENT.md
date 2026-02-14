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

**Decision:** Split the pipeline into mode-specific creative flows (Phases 1-5 for original/inspired_by, Phases 1-2 for adapt) that converge at Phase 6 (image prompt generation). Downstream phases (TTS, images, captions, video) are identical across modes.

**Consequences:**
- Code reuse for media generation phases
- Mode-specific logic is isolated in story_writer.py
- The script.json format must accommodate output from all three modes
- Testing requires covering all three input paths

---

### ADR-003: OpenAI as Primary TTS Provider

**Status:** Accepted

**Context:** Need consistent, affordable narration for 30-120 minute videos. ElevenLabs offers more expressive voices but costs 7-14x more ($22-48 vs $3.24 for 2 hours).

**Decision:** Use OpenAI tts-1-hd as the default provider. Design the TTS generator with a provider abstraction (abstract base class) to allow future ElevenLabs support.

**Consequences:**
- Cost-effective for long-form content (~$7.41 for 30-minute video)
- Clean, consistent voice quality but less expressive range
- Provider abstraction adds a small amount of interface code
- Future providers only need to implement the abstract interface

---

### ADR-004: Craft Notes as Style Consistency Anchor

**Status:** Accepted

**Context:** When generating a multi-scene story across many API calls, voice and style can drift. Each scene is generated in a separate Claude call with limited context.

**Decision:** Phase 1 analyzes the style reference to produce explicit "craft notes" — concrete rules about sentence structure, vocabulary, tone, and pacing. These notes are included in every subsequent generation call as a consistency anchor.

**Consequences:**
- Prevents voice drift across 25+ separate API calls
- Adds ~500-1000 tokens to every scene generation context
- Quality of craft notes directly impacts story consistency
- Works well for original and inspired_by modes; adapt mode skips this

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

**Decision:** Add a dedicated narration prep phase after prose finalization. This produces a parallel `narration_text` field per scene while preserving the original prose. Transformations include: expanding abbreviations, converting numbers to words, inserting pause markers, and smoothing punctuation.

**Consequences:**
- Original prose preserved for display/review
- TTS receives optimized text for better audio quality
- Adds a processing step between writing and audio generation
- Narration prep rules may need tuning per TTS provider

---

## Technical Notes

### Patterns

- **Provider abstraction:** TTS and image generation use abstract base classes to support multiple providers. Each provider implements a common interface (generate method with standard parameters).
- **State tracking via project.json:** All phase and scene statuses tracked in a single JSON file. Statuses follow: pending -> in_progress -> completed/awaiting_review/failed.
- **Running summaries for context management:** Long stories use compressed summaries of prior events to stay within context limits. Each scene generation receives: style reference, craft notes, story bible, outline, previous scene, running summary, and scene beat.

### Gotchas

- DALL-E 3 has no cross-image memory — each image prompt must be fully self-contained with character descriptions
- OpenAI TTS has a character limit per request — long scenes may need chunking
- FFmpeg filter complexity grows with video effects — Ken Burns + blur background + subtitle overlay requires careful filter graph construction

### External Integrations

- **Anthropic Claude API** — Story generation (all creative phases). Uses anthropic Python SDK.
- **OpenAI API** — TTS (tts-1-hd model), image generation (DALL-E 3), caption timing (Whisper). Uses openai Python SDK.
- **FFmpeg** — Video assembly, filters, transitions, subtitle rendering. Called as subprocess.

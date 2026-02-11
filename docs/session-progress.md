# Story Video Generator — Session Progress

Captured: 2026-02-08

This document records all decisions, discussions, and artifacts from the planning
and design sessions, so work can resume from any point.

---

## Project Overview

A Python CLI tool that generates narrated "story videos" for YouTube — the kind
a listener can have on in the background. A topic goes in, a 30-120 minute video
comes out with AI narration, captions, and scene illustrations that pop in/out
over a themed background.

**Tech stack:** Python, Claude API (story writing), OpenAI TTS (narration),
DALL-E 3 (images), Whisper (caption timing), FFmpeg (video assembly).

---

## Artifacts Created

| File | Description |
|------|-------------|
| `docs/creative-story-flow.md` | Full pipeline for original and inspired-by story generation: analysis → craft notes → story bible → outline → scene-by-scene prose → self-critique/revision → image prompts → narration prep |
| `docs/straight-adaptation-flow.md` | Pipeline for narrating an existing story word-for-word: scene splitting → narration flagging → image prompts → narration prep |
| `docs/session-progress.md` | This file |

---

## Key Design Decisions

### 1. Three Input Modes (not two)

The original plan had one story generation mode. We expanded to three:

- **Original** (`original`): User provides a topic, premise, or outline. AI writes
  the story from scratch.
- **Inspired by** (`inspired_by`): User provides an existing story as inspiration.
  AI writes a completely different story capturing similar themes/mood/structure.
- **Adapt** (`adapt`): User provides a finished story. It's narrated word for word.
  AI only handles structural work (scene splitting) and visuals (image prompts).

Each mode has its own pipeline flow documented in the two flow documents above.

### 2. Style Emulation via Sample Text

- Users provide a `style_reference.txt` (1,500-2,500 words of sample prose)
- Recommended for `original` and `inspired_by` modes; not needed for `adapt`
- 2-3 excerpts showing different registers (dialogue, description, tension) work
  best
- Annotated samples are even better: prose + bullet points explaining what makes
  the voice distinctive

### 3. Multi-Phase Creative Pipeline (not single-pass)

The original plan had story generation as a single stage. We redesigned it as
a multi-phase process with human review checkpoints:

```
Phase 1: Analysis + Craft Notes       → checkpoint
Phase 2: Story Bible                  → checkpoint
Phase 3: Outline / Beat Sheet         → checkpoint  ← most important review point
Phase 4: Scene-by-scene prose         → checkpoint
Phase 5: Self-critique + revision     → checkpoint
Phase 6: Image prompt generation
Phase 7: Narration prep
```

**Rationale:** Single-pass generation produces mediocre long-form prose. The
highest-leverage improvement is front-loading structure (outline review) and
adding a self-critique/revision cycle. The style sample + craft notes + story
bible, included in every API call, prevent voice drift across multiple
generation calls.

In **autonomous mode**, all phases run without pausing but critique/revision
still executes automatically.

In **semi-automated mode**, each phase saves state and pauses for human review.

### 4. Craft Notes as Consistency Anchor

Rather than just including a raw style sample in prompts, Phase 1 has Claude
analyze the sample and produce explicit craft rules:

- "Use short declarative sentences during action sequences"
- "Dialogue should be clipped; characters rarely say exactly what they mean"
- "Avoid adverbs on dialogue attribution"

These rules, combined with the story bible, are included in every subsequent
generation call. This produces tighter style adherence than raw sample
pattern-matching alone.

### 5. Scene-by-Scene Generation with Context Management

Each scene generation call receives:

| Context piece | ~Size | Purpose |
|---------------|-------|---------|
| Style reference excerpt | 1,500 words | Voice anchor |
| Craft notes | 500 words | Explicit writing rules |
| Story bible | 800 words | Character/setting consistency |
| Full outline | 1,000 words | Structural awareness |
| Previous scene ending | 500 words | Voice and narrative continuity |
| Running summary | 200 words/chapter | Plot continuity without full context |
| This scene's beat | 100 words | What to write now |

Running summaries compress older events so the model stays plot-aware without
exhausting context on very long stories (60+ scenes).

### 6. Narration Prep Phase (TTS Optimization)

Added a narration prep step between finalized text and TTS for both flows:

- Expands abbreviations and numbers for speech ("Dr." → "Doctor", "1920s" →
  "nineteen-twenties")
- Inserts pause markers at dramatic transitions
- Smooths punctuation that trips up TTS (em dashes, nested parentheticals)
- Cleans up anything flagged in the narration flagging phase (adapt mode)
- Preserves original text; produces a parallel `narration_text` field

**Rationale:** OpenAI TTS doesn't support SSML. These light text transformations
are the main lever for improving spoken delivery quality.

### 7. TTS Provider: Start with OpenAI, ElevenLabs Optional Later

**Cost comparison for a 2-hour narration (~108,000 characters):**

| Provider | Model/Plan | Cost |
|----------|-----------|------|
| OpenAI | gpt-4o-mini-tts | $0.07 |
| OpenAI | tts-1 (standard) | $1.62 |
| OpenAI | tts-1-hd | $3.24 |
| ElevenLabs | Creator plan (minimum needed) | $22/month |

**Decision:** Start with OpenAI tts-1-hd. It's clean, consistent, and good for
audiobook-style narration. ElevenLabs offers more expressive delivery (emotion
control, whisper, voice cloning) but at 7-14x the cost. The TTS generator will
be designed with a provider abstraction so ElevenLabs can be added later without
pipeline changes.

### 8. OpenAI TTS Vocal Limitations (Accepted)

OpenAI TTS does not support:
- Whisper/shout effects
- Per-line emotion or intensity control
- Distinct character voices
- SSML markup

This is acceptable for audiobook-style "steady narrator" delivery. The text
itself carries emotional cues ("she whispered") and the listener's imagination
fills in the rest — same as a professional audiobook narrator.

The narration prep phase is the main mitigation: pause insertion, pacing via
paragraph structure, and clean punctuation help the TTS deliver the best it can.

### 9. Image Prompts Generated After Prose (Not During)

Image prompt generation is a separate phase that runs after prose is finalized.
This keeps story generation calls focused on prose quality. Each prompt is
self-contained (DALL-E has no cross-image memory) and includes consistent
character descriptions for visual continuity.

---

## Revised Pipeline Flow (Both Modes Combined)

```
                    ┌─────────── adapt ───────────┐
                    │                              │
                    │  Phase 1: Scene Splitting    │
                    │  Phase 2: Narration Flagging │
                    │                              │
                    └──────────┬───────────────────┘
                               │
         ┌── original / inspired_by ──┐
         │                            │
         │  Phase 1: Analysis         │
         │  Phase 2: Story Bible      │
         │  Phase 3: Outline          │
         │  Phase 4: Scene Prose      │
         │  Phase 5: Critique/Revise  │
         │                            │
         └────────────┬───────────────┘
                      │
                      ▼
         Phase 6: Image Prompt Generation
         Phase 7: Narration Prep
                      │
                      ▼
         Cost Estimate → User Confirmation
                      │
              ┌───────┴───────┐
         3a. TTS         3b. Images     ← parallel, async
              └───────┬───────┘
                      │
                      ▼
         4. Caption Generation (Whisper)
                      │
                      ▼
         5. Video Assembly (FFmpeg)
                      │
                      ▼
         6. Final Output
```

---

## Updated Project Structure

```
create-videos/
├── pyproject.toml
├── .env.example
├── config.yaml
├── docs/
│   ├── creative-story-flow.md
│   ├── straight-adaptation-flow.md
│   └── session-progress.md
├── src/
│   └── story_video/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── models.py
│       ├── state.py
│       ├── cost.py
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── orchestrator.py
│       │   ├── story_writer.py       # Handles all 3 input modes
│       │   ├── tts_generator.py      # OpenAI TTS (ElevenLabs later)
│       │   ├── image_generator.py
│       │   ├── caption_generator.py
│       │   └── video_assembler.py
│       ├── ffmpeg/
│       │   ├── __init__.py
│       │   ├── filters.py
│       │   ├── transitions.py
│       │   ├── subtitles.py
│       │   └── commands.py
│       └── utils/
│           ├── __init__.py
│           ├── text.py
│           └── retry.py
├── output/
│   └── {project-id}/
│       ├── project.json
│       ├── script.json
│       ├── craft_notes.md            # NEW (creative flow)
│       ├── story_bible.md            # NEW (creative flow)
│       ├── outline.md                # NEW (creative flow)
│       ├── revision_notes.md         # NEW (creative flow)
│       ├── narration_flags.md        # NEW (adapt flow)
│       ├── scenes/                   # Per-scene text files for review
│       ├── audio/
│       ├── images/
│       ├── captions/
│       ├── video/
│       └── final.mp4
└── tests/
```

---

## Updated Data Models (models.py)

Changes from original plan:

- **`Project`** gains: `input_mode` (original | inspired_by | adapt),
  `style_reference_path`, `source_material_path`
- **`Scene`** gains: `narration_text` (TTS-optimized version, separate from
  original text)
- **`StyleConfig`** gains: `tts_provider` (openai | elevenlabs), to allow
  switching later
- New model: **`CraftNotes`** or store as plain markdown referenced by path
- New model: **`StoryBible`** or store as plain markdown referenced by path

---

## Implementation Order (Unchanged)

The order from the original plan still holds. The story_writer.py step (step 4)
is now larger due to the multi-phase creative pipeline, but the sequencing of
all other steps is the same:

1. models.py + config.py + state.py
2. utils/text.py
3. cost.py
4. pipeline/story_writer.py (now covers all 3 modes + all creative phases)
5. pipeline/tts_generator.py
6. pipeline/image_generator.py
7. pipeline/caption_generator.py
8. ffmpeg/*
9. pipeline/video_assembler.py
10. pipeline/orchestrator.py
11. cli.py
12. pyproject.toml + .env.example + config.yaml

---

## Open Questions / Not Yet Discussed

- **Video assembly details:** Ken Burns effect parameters, background blur
  approach, transition timing, subtitle styling — all per the original plan but
  not yet discussed in detail.
- **Long story batching:** For 60+ scenes, the plan calls for batching FFmpeg
  work in groups of 10. Not yet discussed.
- **Resume/retry mechanics:** How project.json state tracking works, how failed
  scenes are retried. Not yet discussed.
- **CLI interface details:** Exact command structure, flags, options. Not yet
  discussed.
- **Testing strategy:** Not yet discussed.
- **Config.yaml defaults:** Exact default values for voices, image quality,
  video settings. Not yet discussed.
- **Cost estimation formula:** Exact breakdown for the `estimate` command. Not
  yet discussed.

---

## Dependencies

```
anthropic, openai, pydantic>=2.0, typer[all], pyyaml, python-dotenv, tenacity, rich
```

System requirement: FFmpeg (assumed already installed).

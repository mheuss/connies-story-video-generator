# Story Video Generator — Design Document

Consolidates all design decisions from the planning sessions (Feb 8-11, 2026).
This is the single source of truth for the project's architecture and behavior.

---

## 1. Project Overview

A Python CLI tool that generates narrated "story videos" for YouTube. A topic goes
in, a 30-120 minute video comes out with AI narration, captions, and scene
illustrations that pop in/out over a themed background.

**Tech stack:** Python, Claude API (story writing), OpenAI TTS (narration),
DALL-E 3 (images), Whisper (caption timing), FFmpeg (video assembly).

**Dependencies:**
```
anthropic, openai, pydantic>=2.0, typer[all], pyyaml, python-dotenv, tenacity, rich
```

System requirement: FFmpeg (assumed installed).

---

## 2. Three Input Modes

| Mode | Input | AI Role |
|------|-------|---------|
| `original` | Topic, premise, or outline | Writes the story from scratch |
| `inspired_by` | Existing story as inspiration | Writes a different story capturing similar themes/mood |
| `adapt` | Finished story | Narrates word for word; AI handles structure and visuals only |

Each mode feeds into its own pipeline flow. See sections 4 and 5.

---

## 3. Pipeline Overview

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
         TTS Generation   Image Generation    ← parallel
              └───────┬───────┘
                      │
                      ▼
         Caption Generation (Whisper)
                      │
                      ▼
         Video Assembly (FFmpeg)
                      │
                      ▼
         Final Output
```

In **autonomous mode**, all phases run without pausing. Critique/revision still
executes automatically.

In **semi-automated mode** (the default), each phase saves state and pauses for
human review. The user edits intermediate files, then runs `resume` to continue.

---

## 4. Creative Story Flow (original / inspired_by)

Full details in `docs/creative-story-flow.md`. Summary of each phase:

### Phase 1: Analysis + Craft Notes

- Analyzes `style_reference.txt` to produce explicit craft rules
- For `inspired_by`: also analyzes themes and structure of source material
- Output: `craft_notes.md`
- These rules are included in every subsequent generation call

### Phase 2: Story Bible

- Establishes characters, setting, tone, terminology
- Input: craft notes + topic/premise
- Output: `story_bible.md`
- Included in every subsequent generation call for consistency

### Phase 3: Outline / Beat Sheet

- Scene-by-scene structural plan with emotional beats and pacing
- Target: ~5 scenes per 10 minutes, ~1,800 words per scene
- Output: `outline.md`
- **Most important review checkpoint** — restructuring an outline is cheap

### Phase 4: Scene-by-Scene Prose

- One Claude API call per scene
- Each call receives: style reference excerpt (~1,500w), craft notes (~500w),
  story bible (~800w), full outline (~1,000w), previous scene ending (~500w),
  running summary (~200w/chapter), this scene's beat (~100w)
- Running summaries compress older events for long stories
- Output: `scenes/scene_01.md`, etc. + `script.json`

### Phase 5: Self-Critique and Revision

- Critique pass identifies voice drift, cliches, inconsistencies, pacing issues
- Output: `revision_notes.md`
- Revision pass rewrites flagged scenes
- Originals preserved as `scene_01.original.md`
- One revision pass is usually sufficient; two at most

---

## 5. Straight Adaptation Flow (adapt)

Full details in `docs/straight-adaptation-flow.md`. Summary:

### Phase 1: Scene Splitting

- Divides source story into scenes at natural boundaries
- Preserves every word exactly
- Target: 1,500-2,000 words per scene
- Rules: never split mid-paragraph or mid-dialogue

### Phase 2: Narration Flagging

- Identifies TTS-unfriendly content (footnotes, visual formatting, unusual typography)
- For well-written prose, usually produces zero flags
- Fixes applied to `narration_text` only; original text never modified

---

## 6. Shared Phases (Both Flows)

### Phase 6: Image Prompt Generation

- Runs after prose is finalized
- One DALL-E prompt per scene, self-contained (no cross-image memory)
- Includes consistent character descriptions for visual continuity
- Style prefix from config prepended to each prompt
- Output: image prompts in `script.json`

### Phase 7: Narration Prep (TTS Optimization)

- Produces a `narration_text` version optimized for spoken delivery
- Expands abbreviations and numbers ("Dr." → "Doctor", "1920s" → "nineteen-twenties")
- Inserts pause markers at dramatic transitions
- Smooths punctuation that trips up TTS (em dashes, nested parentheticals)
- Original text always preserved; `narration_text` is a parallel field

---

## 7. Style Emulation

- Users provide a `style_reference.txt` (1,500-2,500 words of sample prose)
- Recommended for `original` and `inspired_by`; not needed for `adapt`
- 2-3 excerpts showing different registers work best
- Annotated samples (prose + notes on what makes the voice distinctive) are even better
- Phase 1 converts the sample into explicit craft rules, which are the real
  consistency anchor across all subsequent API calls

---

## 8. TTS Provider

**Start with OpenAI, ElevenLabs optional later.**

Cost comparison for a 2-hour narration (~108,000 characters):

| Provider | Model | Cost |
|----------|-------|------|
| OpenAI | gpt-4o-mini-tts | $0.07 |
| OpenAI | tts-1 (standard) | $1.62 |
| OpenAI | tts-1-hd | $3.24 |
| ElevenLabs | Creator plan | $22/month |

Default: `tts-1-hd`. Clean, consistent, good for audiobook-style narration.

Accepted limitations: no whisper/shout effects, no per-line emotion control,
no distinct character voices, no SSML. Acceptable for steady narrator delivery.
The narration prep phase is the main mitigation.

TTS generator designed with a provider abstraction so ElevenLabs can be added
later without pipeline changes.

---

## 9. Video Assembly

### Ken Burns Effect

- Zoom range: 1.0 → 1.08 (subtle 8% over scene duration)
- Direction: randomly selected per scene — zoom in, zoom out, pan left, pan right,
  or diagonal drift
- Duration: matches scene audio length
- Easing: linear

### Background

- **Default:** Blurred enlargement of the scene image. Scale to fill 1920x1080,
  apply Gaussian blur (radius ~40px), overlay sharp image centered on top.
- **Optional override:** User-provided custom background image via config.

### Transitions

- Between scenes: crossfade over ~1.5 seconds
- Video start: fade from black, ~2 seconds
- Video end: fade to black, ~3 seconds

### Subtitles

- Font: Montserrat (fallback: Arial)
- Size: 48px at 1080p
- Color: white (#FFFFFF) with black outline (#000000, 3px)
- Position: bottom center, 80px from bottom edge
- Max 42 characters per line, max 2 lines
- Timed to Whisper word timestamps; no karaoke-style word highlighting

### Per-Scene Segment Assembly

Each scene is rendered as an independent video segment (`segment_01.mp4`), then
all segments are concatenated with crossfade transitions in a final pass.

Benefits:
- Failed scenes only require re-rendering that one segment
- Natural resume capability — skip segments that already exist
- Easy to preview individual scenes

If FFmpeg struggles with large concat operations (60+ segments), batch into
groups of 10-15 → chapter files → final concat. Add this optimization only if
needed.

---

## 10. Resume / Retry Mechanics

### State tracking via `project.json`

Tracks status at two levels:

**Phase level:**
```
pending → in_progress → completed
                     → awaiting_review (semi-automated mode)
                     → failed
```

**Scene level** (per asset):
```
pending → in_progress → completed
                     → failed
```

Each scene tracks: `text`, `narration_text`, `audio`, `image`, `captions`,
`video_segment`.

### Resume behavior

1. Load `project.json`
2. Find `current_phase`
3. Skip scenes marked `completed`
4. Retry scenes marked `failed`
5. Process scenes marked `pending`
6. When all scenes complete, advance to next phase

### Retry behavior

- API calls use exponential backoff with 3 retries (via `tenacity`)
- If all retries fail: mark scene step as `failed`, continue to next scene
- On `resume`: only failed scenes are retried

### Rules

- Never overwrite a completed artifact
- Failed scenes don't block other scenes in the same phase
- Failed scenes DO block downstream steps for that specific scene
  (no captions without audio, no video segment without audio + image)

---

## 11. CLI Interface

### Commands

```
story-video create    — start a new project
story-video resume    — continue a paused/failed project
story-video estimate  — show cost estimate without starting
story-video status    — show current state of a project
story-video list      — list all projects
```

### `create`

```
story-video create \
  --mode original|inspired_by|adapt \
  --topic "A lighthouse keeper discovers..." \
  --source-material path/to/story.txt \
  --style-reference path/to/style_sample.txt \
  --duration 30 \
  --voice nova \
  --autonomous \
  --output-dir ./output \
  --config ./config.yaml
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--mode` | Yes | — | `original`, `inspired_by`, or `adapt` |
| `--topic` | For `original` | — | Premise or topic (string or path to file) |
| `--source-material` | For `inspired_by`, `adapt` | — | Path to source story |
| `--style-reference` | No | — | Path to style sample prose |
| `--duration` | No | 30 | Target duration in minutes |
| `--voice` | No | From config | OpenAI TTS voice name |
| `--autonomous` | No | false | Skip human review checkpoints |
| `--output-dir` | No | `./output` | Where projects are stored |
| `--config` | No | `./config.yaml` | Path to config file |

Validation:
- `original` requires `--topic`
- `inspired_by` requires `--source-material`
- `adapt` requires `--source-material`

### `resume`

```
story-video resume [PROJECT_ID]
```

No project ID → resumes most recent project.

### `estimate`

Same flags as `create`. Calculates and prints cost breakdown without starting.

### `status`

```
story-video status [PROJECT_ID]
```

Prints phase and per-scene status table.

### `list`

Lists all projects with mode, status, and creation date.

---

## 12. Cost Estimation

### Formula

```
scene_count = target_duration_minutes * words_per_minute / scene_word_target
characters  = scene_count * scene_word_target * 5.5
```

### Per-service costs

**Claude API (story generation):**
- `original` / `inspired_by`: ~$2-5 for 25 scenes
  (3 setup calls + N scenes + N critique + 0.5N revision + ~4 utility calls)
- `adapt`: ~$0.20-0.50 (~6 calls total)

**OpenAI TTS:**

| Model | Per 1M chars | 25 scenes (~247K chars) |
|-------|-------------|------------------------|
| gpt-4o-mini-tts | $0.60 | $0.15 |
| tts-1 | $15.00 | $3.71 |
| tts-1-hd | $30.00 | $7.41 |

**DALL-E 3:**

| Quality | Per image | 25 scenes |
|---------|----------|-----------|
| standard 1024x1024 | $0.040 | $1.00 |
| hd 1024x1024 | $0.080 | $2.00 |

**Whisper:**
```
$0.006 per minute of audio
30 minutes = $0.18
```

### Display format

Shown in two contexts:
1. **`estimate` command** — uses projected scene counts from the formula above.
   Labeled as an estimate.
2. **In-pipeline prompt** (after narration prep, before paid generation) — uses
   actual scene counts and character counts from finalized text. More accurate.

```
Story Video Cost Estimate
─────────────────────────
Mode:     original
Duration: 30 minutes (~25 scenes)

  Claude (story generation)    $2.00 - $5.00
  OpenAI TTS (tts-1-hd)       $7.41
  DALL-E 3 (standard)         $1.00
  Whisper (captions)           $0.18
                              ─────────────
  Estimated total              $10.59 - $13.59
```

---

## 13. Configuration Defaults

```yaml
story:
  target_duration_minutes: 30
  words_per_minute: 150
  scene_word_target: 1800
  scene_word_min: 500
  scene_word_max: 3000

tts:
  provider: openai
  model: tts-1-hd
  voice: nova
  speed: 1.0
  output_format: mp3

images:
  provider: openai
  model: dall-e-3
  size: 1024x1024
  quality: standard
  style: vivid
  style_prefix: "Cinematic digital painting, dramatic lighting:"

video:
  resolution: 1920x1080
  fps: 30
  codec: libx264
  crf: 18
  background_mode: blur
  background_blur_radius: 40
  background_image: null
  ken_burns_zoom: 1.08
  transition_duration: 1.5
  fade_in_duration: 2.0
  fade_out_duration: 3.0

subtitles:
  font: Montserrat
  font_fallback: Arial
  font_size: 48
  color: "#FFFFFF"
  outline_color: "#000000"
  outline_width: 3
  position_bottom: 80
  max_chars_per_line: 42
  max_lines: 2

pipeline:
  autonomous: false
  max_retries: 3
  retry_base_delay: 2
  save_originals_on_revision: true

output:
  directory: ./output
```

---

## 14. Project Structure

```
story-video/
├── pyproject.toml
├── .env.example
├── config.yaml
├── docs/
│   ├── design.md                 ← this file
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
│       │   ├── story_writer.py
│       │   ├── tts_generator.py
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
│       ├── craft_notes.md
│       ├── story_bible.md
│       ├── outline.md
│       ├── revision_notes.md
│       ├── narration_flags.md
│       ├── scenes/
│       ├── audio/
│       ├── images/
│       ├── captions/
│       ├── video/
│       └── final.mp4
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_config.py
    ├── test_state.py
    ├── test_cost.py
    ├── test_text.py
    ├── test_ffmpeg_commands.py
    ├── test_story_writer.py
    ├── test_tts_generator.py
    ├── test_orchestrator.py
    └── ...
```

---

## 15. Testing Strategy

### Layer 1: Unit tests (no API calls, no FFmpeg)

Fast tests covering pure logic:
- `models.py` — validation, serialization, edge cases
- `config.py` — loading, defaults, merging, validation
- `state.py` — transitions, resume logic, failure handling rules
- `cost.py` — calculation math
- `utils/text.py` — narration prep transformations
- `ffmpeg/commands.py` — correct command string construction
- `ffmpeg/filters.py` — filter chain construction

### Layer 2: Integration tests with mocked APIs

Mock API clients, verify pipeline logic:
- `story_writer.py` — correct call sequence, context assembly, running summaries
- `tts_generator.py` — file writing, retry logic, failure recording
- `image_generator.py` — same pattern
- `orchestrator.py` — full pipeline ordering, state management, checkpoint pausing

### Layer 3: Smoke tests (optional, real calls)

Marked `@pytest.mark.slow`, skipped by default:
- One real Claude call, one TTS clip, one DALL-E image, one FFmpeg segment
- Confirms integrations work; not part of regular suite

### Tools

- pytest
- pytest-mock or unittest.mock
- No heavy fixtures

---

## 16. Implementation Order

1. `pyproject.toml` + `.env.example` + `config.yaml` (project bootstrap)
2. `models.py` + `config.py` + `state.py`
3. `utils/text.py`
4. `cost.py`
5. `pipeline/story_writer.py` (all 3 modes, all creative phases)
6. `pipeline/tts_generator.py`
7. `pipeline/image_generator.py`
8. `pipeline/caption_generator.py`
9. `ffmpeg/*`
10. `pipeline/video_assembler.py`
11. `pipeline/orchestrator.py`
12. `cli.py`

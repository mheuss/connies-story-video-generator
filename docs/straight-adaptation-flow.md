# Straight Adaptation Flow

How the pipeline handles a complete, pre-written story — producing a narrated
video from existing text without modifying the prose.

## Applies To

- **Adapt mode**: User provides a finished story. The text is narrated word for
  word. The AI's role is purely structural (scene splitting) and visual (image
  prompts), not creative.

## Input Files

| File | Required | Description |
|------|----------|-------------|
| `source_story.txt` | Yes | The complete story text to be narrated. |
| `style_reference.txt` | No | Not needed — the story *is* the style. Only useful if you want image prompts to match a specific visual aesthetic beyond what the text implies. |

## Phase Overview

```
Phase 1: Scene Splitting              → human review checkpoint
Phase 2: Narration Flagging           → human review checkpoint (if flags found)
Phase 3: Image Prompt Generation
Phase 4: Narration Prep (TTS optimization)
            ↓
      Standard pipeline (cost estimate → TTS → images → captions → video)
```

This flow is significantly shorter than the creative flow. There is no story
bible, no outline, no critique, no revision. The text is treated as final.

---

## Phase 1: Scene Splitting

**Purpose:** Divide the story into scenes for individual TTS generation, image
assignment, and video segments.

**Input:** `source_story.txt`

**Claude is asked to:**

1. Read the full text
2. Identify natural scene boundaries:
   - Chapter or section breaks (explicit in the text)
   - Setting changes (new location, time jump)
   - Major tonal shifts
   - POV changes
   - Natural dramatic pauses / act breaks
3. Split the text into scenes, preserving every word exactly
4. For each scene, provide:
   - Scene number and a short descriptive title (for internal reference)
   - The complete, unmodified text of that scene
   - Estimated narration duration based on word count (~150 words/minute)

**Target scene length:** 1,500-2,000 words (~2-3 minutes of narration). This
keeps each video segment visually interesting — long enough for the image to
breathe, short enough that the viewer isn't staring at one illustration for
5+ minutes.

**Splitting rules:**
- Never split mid-paragraph
- Never split mid-dialogue (keep a full exchange together)
- Prefer splitting at existing whitespace/section breaks in the source
- If a natural scene runs long (3,000+ words), find the best internal break
  point — usually a paragraph that shifts focus or a moment of pause
- If a natural scene is very short (under 500 words), consider merging with
  an adjacent scene unless it's a deliberate dramatic beat

**Output:** `script.json` with scene objects, each containing the full scene text.
Also `scenes/scene_01.md`, `scene_02.md`, etc. for easy human review.

**Review checkpoint (semi-automated mode):** Human reviews the splits. Common
adjustments:
- Moving a split point a paragraph earlier or later
- Merging two scenes that were split too aggressively
- Splitting a long scene that should have two distinct images
- This is usually quick — most splits are obvious from the text structure.

---

## Phase 2: Narration Flagging

**Purpose:** Identify anything in the text that won't work well as spoken audio.

**Input:** Scene texts from Phase 1.

**Claude scans for:**

| Flag | Example | Suggested fix |
|------|---------|---------------|
| Footnotes / endnotes | `[1]`, `*see appendix` | Remove or inline the content |
| Visual formatting | "as shown in the table above" | Rephrase or cut |
| Unusual typography | ALL CAPS for emphasis, `s p a c e d` text | Normalize |
| Very long parentheticals | Nested asides that lose the listener | Suggest simplification |
| Non-prose content | Poems with complex line breaks, lists, letters | Flag for manual decision |
| Ambiguous pronunciation | Unusual proper nouns, invented words | Flag for phonetic note |

**For most well-written narrative prose, this phase produces zero or very few
flags.** It exists as a safety net, not a bottleneck.

**Output:** `narration_flags.md` listing each flag with its location and
suggested resolution.

**Review checkpoint (semi-automated mode):** Only pauses if flags were found.
Human reviews each flag and decides: accept the suggested fix, provide their own
fix, or leave it as-is. If no flags, this phase is skipped entirely.

**Important:** Any fixes here are applied to the `narration_text` field only.
The original text in `source_story.txt` is never modified.

---

## Phase 3: Image Prompt Generation

**Purpose:** Create a DALL-E prompt for each scene's illustration.

For each scene, Claude:
- Reads the scene text
- Identifies the strongest visual moment — the image the listener would picture
- Generates a self-contained image prompt (DALL-E has no cross-image memory)
- Maintains visual consistency by including character descriptions and setting
  details in every prompt (extracted from the story text itself)

**Prompt structure:**
```
[Style prefix from config, e.g., "Cinematic digital painting, dramatic lighting:"]
[Scene description focusing on the key visual moment]
[Character details relevant to this scene]
[Mood/atmosphere: lighting, weather, color palette]
```

**Visual consistency note:** Since DALL-E generates each image independently,
character appearances can drift between scenes. The prompts should include
consistent physical descriptions for recurring characters. Claude extracts these
from the story text and re-includes them in each relevant prompt.

**Output:** Image prompts added to `script.json` scene objects.

---

## Phase 4: Narration Prep

**Purpose:** Optimize the text for spoken delivery via TTS.

For each scene, produce a `narration_text` version that:

- **Preserves the original prose** as closely as possible — this is an adaptation,
  not a rewrite
- **Expands abbreviations:** "Dr." → "Doctor", "St." → "Street" or "Saint"
  (context-dependent), "Mr." → "Mister"
- **Expands numbers:** "1920s" → "nineteen-twenties", "$500" → "five hundred
  dollars", "3rd" → "third"
- **Inserts pause markers** at scene transitions and major dramatic beats
  (paragraph breaks that the TTS engine will interpret as pauses)
- **Smooths punctuation** that trips up TTS: replaces em dashes with commas or
  periods where appropriate, simplifies nested punctuation
- **Applies narration flag fixes** from Phase 2 (if any)

The goal is that someone reading `narration_text` aloud would produce the same
experience as reading the original — just with fewer stumbles.

**Output:** `narration_text` field populated in `script.json` for each scene.

---

## What This Flow Does NOT Do

- **Does not rewrite or "improve" the prose.** The text is the text.
- **Does not add or remove content.** Scene splits are structural, not editorial.
- **Does not require a style reference.** The story provides its own voice.
- **Does not run critique or revision passes.** Those are for AI-generated text
  that might need quality improvement. User-provided text is assumed final.

---

## Estimated API Costs (Adaptation Flow)

For a 60-minute story (~9,000 words, ~30 scenes):

| Phase | API Calls | Service |
|-------|-----------|---------|
| Scene splitting | 1-2 | Claude |
| Narration flagging | 1 | Claude |
| Image prompt generation | 1-2 | Claude |
| Narration prep | 1-2 | Claude |
| TTS generation | ~30-60 | OpenAI TTS |
| Image generation | ~30 | DALL-E 3 |
| Caption generation | ~30 | Whisper |

**Claude calls: ~5-7** (vs. ~80 for creative flow). This is dramatically cheaper
on the story generation side. The TTS, image, and video costs are identical
between both flows.

---

## Quick Reference: Creative vs. Adaptation

| Aspect | Creative Flow | Adaptation Flow |
|--------|---------------|-----------------|
| Story source | AI-generated | User-provided |
| Claude API calls (story phase) | ~80 | ~5-7 |
| Human review checkpoints | 5 | 1-2 |
| Style reference needed | Yes (recommended) | No |
| Story bible | Yes | No |
| Outline phase | Yes | No |
| Critique/revision | Yes | No |
| Text modification | Extensive (it's being written) | Minimal (narration prep only) |
| Best for | Original content, inspired-by | Existing stories, public domain works |

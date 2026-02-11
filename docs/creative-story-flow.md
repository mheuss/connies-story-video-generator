# Creative Story Generation Flow

How the pipeline produces original or inspired stories with high-quality prose,
consistent voice, and iterative human review.

## Applies To

- **Original creation**: User provides a topic, premise, or outline. The AI writes the story from scratch.
- **Inspired by**: User provides an existing story as inspiration. The AI writes a completely different story that captures similar themes, mood, or structure.

## Input Files

| File | Required | Description |
|------|----------|-------------|
| `style_reference.txt` | Recommended | 1,500-2,500 words of sample prose whose voice/tone to emulate. Best as 2-3 excerpts showing different registers (dialogue, description, tension). |
| `source_material.txt` | For "inspired by" mode | The existing story to draw inspiration from. |
| Topic / premise | For "original" mode | Provided via CLI argument. Can be a sentence or several paragraphs. |

## Phase Overview

```
Phase 1: Analysis + Craft Notes       → human review checkpoint
Phase 2: Story Bible                  → human review checkpoint
Phase 3: Outline / Beat Sheet         → human review checkpoint  ← most important
Phase 4: Scene-by-scene prose         → human review checkpoint
Phase 5: Self-critique + revision     → human review checkpoint
Phase 6: Image prompt generation
Phase 7: Narration prep (TTS optimization)
            ↓
      Standard pipeline (cost estimate → TTS → images → captions → video)
```

In **autonomous mode**, all phases run without pausing. The critique/revision pass
(Phase 5) still executes automatically. Quality is lower than with human review
but significantly better than single-pass generation.

In **semi-automated mode**, each phase saves state and pauses. The user can review
and edit any intermediate file, then `resume` to continue.

---

## Phase 1: Analysis + Craft Notes

**Purpose:** Understand *what* to emulate before writing anything.

**Input:** `style_reference.txt` and (for "inspired by" mode) `source_material.txt`

**Claude is asked to produce:**

1. **Voice analysis** of the style reference:
   - Sentence structure patterns (short/long, simple/complex, fragments)
   - Vocabulary register (literary, conversational, sparse, ornate)
   - Use of metaphor and imagery (frequent/rare, drawn from what domains)
   - Dialogue style (clipped, naturalistic, stylized, subtext-heavy)
   - Narrative distance (close third, distant, first-person intimate)
   - Pacing techniques (how tension builds, how scenes breathe)

2. **Thematic analysis** (for "inspired by" mode):
   - Core themes and emotional undertones
   - Structural approach (how the story is built, what makes it work)
   - What to carry forward vs. what to leave behind

3. **Craft rules** — explicit directives for later generation:
   - "Use short declarative sentences during action sequences"
   - "Dialogue should be clipped; characters rarely say exactly what they mean"
   - "Descriptions favor sound and texture over visual detail"
   - "Avoid adverbs on dialogue attribution"

**Output:** `craft_notes.md`

**Why this matters:** Including a style sample alone makes Claude pattern-match
loosely. Forcing it to articulate *what* to emulate produces much tighter adherence
to voice across subsequent calls. These craft rules are the consistency anchor.

**Review checkpoint:** Human reads `craft_notes.md`, adjusts the rules, adds
their own ("I want more humor than the sample shows", "Keep chapters short").

---

## Phase 2: Story Bible

**Purpose:** Establish characters, setting, and tone before writing prose.

**Input:** Craft notes + topic/premise (or thematic analysis from Phase 1)

**Claude is asked to produce:**

1. **Characters:**
   - Name, age, key physical details
   - Personality in 2-3 sentences
   - Speech patterns (formal, uses slang, speaks in questions, etc.)
   - Relationships to other characters
   - Internal conflict / motivation

2. **Setting:**
   - Time period, location, world rules
   - Sensory palette: what does this world smell/sound/feel like?
   - Atmosphere and mood

3. **Tone guide:**
   - Overall emotional register
   - How humor is used (if at all)
   - Level of darkness/lightness
   - Narrative voice reminders (drawn from craft notes)

4. **Key terminology / proper nouns:**
   - Place names, character-specific terms, invented words
   - Ensures consistency across scenes

**Output:** `story_bible.md`

**Why this matters:** This document is included in *every* subsequent generation
call. Without it, characters drift — names get inconsistent, personality flattens,
settings lose specificity. The story bible is cheap to produce and prevents the
most common quality problems in multi-call generation.

**Review checkpoint:** Human adjusts characters, adds details, changes setting
specifics, etc. This is a high-leverage edit point.

---

## Phase 3: Outline / Beat Sheet

**Purpose:** Lock down structure and pacing before writing any prose.

**Input:** Craft notes + story bible + topic/premise

**Claude is asked to produce:**

For each scene:
- **Scene number and title**
- **What happens** (2-3 sentences of plot)
- **Emotional beat** (what the reader should feel)
- **Purpose** in the larger arc (introduces character, raises stakes, provides relief, etc.)
- **Estimated word count** (~1,500-2,000 words per scene, ~2-3 min narration)

Plus:
- **Pacing notes:** where tension peaks, where it releases, where quiet moments land
- **Arc summary:** the overall shape of the story (setup → complication → escalation → climax → resolution)
- **Target scene count** based on requested duration (~5 scenes per 10 minutes)

**Output:** `outline.md`

**This is the most important review checkpoint.** Restructuring an outline costs
nothing. Restructuring 12,000 words of written prose is painful and usually
results in compromise. Get the bones right here.

**Review checkpoint:** Human reorders scenes, cuts what's unnecessary, adds beats
that are missing, adjusts pacing. Can be as light as "looks good" or as heavy as
rewriting half the outline.

---

## Phase 4: Scene-by-Scene Prose Generation

**Purpose:** Write the actual story.

**Method:** One Claude API call per scene. Each call receives:

| Context piece | Size | Purpose |
|---------------|------|---------|
| Style reference excerpt | ~1,500 words | Voice anchor |
| Craft notes | ~500 words | Explicit writing rules |
| Story bible | ~800 words | Character/setting consistency |
| Full outline | ~1,000 words | Structural awareness (knows what's coming) |
| Previous scene ending | ~500 words | Voice and narrative continuity |
| Running summary | ~200 words per chapter so far | Plot continuity without full context |
| This scene's beat | ~100 words | What to write now |

**Total context per call:** ~4,000-5,000 words of reference + generation room for
~1,500-2,000 words of prose. Well within Claude's context window.

**Generation instructions include:**
- Write only this scene; stop at the scene boundary
- Follow the craft rules precisely
- Match the voice of the style reference
- Use character speech patterns from the story bible
- Hit the emotional beat specified in the outline
- Target the estimated word count

**The running summary** is critical for longer stories. After each scene is
generated, Claude produces a 2-3 sentence summary of what happened. These
accumulate and compress older events, keeping the model aware of the full plot
without exhausting context.

**Output:** `scenes/scene_01.md`, `scene_02.md`, etc. + `script.json` with
structured scene data.

**Review checkpoint:** Human reads through the scenes. Can edit any scene file
directly. Edits are preserved on resume.

---

## Phase 5: Self-Critique and Revision

**Purpose:** Catch quality drift, generic writing, and inconsistencies.

**Step 1 — Critique pass.** For each scene, Claude receives:
- The scene text
- The style reference
- The craft notes
- Adjacent scene endings (for continuity)

Claude is asked to identify:
- Where the voice drifted from the style reference
- Generic or cliched phrasing
- Telling instead of showing
- Inconsistencies with the story bible
- Pacing problems (too rushed, too slow)
- Dialogue that sounds unnatural or on-the-nose

**Output:** `revision_notes.md` — specific, actionable notes per scene.

**Step 2 — Human review of critique.** The human:
- Reads the revision notes
- Marks scenes as "fine as-is", "revise", or "I'll edit this myself"
- Adds their own notes for scenes that need specific changes
- In autonomous mode, all scenes with non-trivial critique are auto-revised

**Step 3 — Revision pass.** For flagged scenes, Claude receives:
- The original scene text
- The specific critique/revision notes
- The style reference and craft notes
- Adjacent scenes for continuity

Claude rewrites the scene, focusing on the identified issues.

**Output:** Updated scene files. Originals preserved as `scene_01.original.md`.

**One revision pass is usually sufficient.** Two at most. Diminishing returns
after that — further improvements are better made by direct human editing.

---

## Phase 6: Image Prompt Generation

**Purpose:** Create DALL-E prompts for each scene's visual.

**Runs after prose is finalized.** This is intentionally separated from story
writing to keep those calls focused on prose quality.

For each scene, Claude:
- Identifies the strongest visual moment
- Generates a self-contained image prompt (DALL-E has no cross-image memory)
- Incorporates the story's visual style/mood
- Adds a style prefix from config (e.g., "Cinematic digital art, dramatic lighting:")

**Output:** Image prompts added to `script.json` scene objects.

---

## Phase 7: Narration Prep

**Purpose:** Optimize finalized text for spoken delivery via TTS.

For each scene, Claude produces a `narration_text` version that:
- Preserves the original prose exactly where possible
- Inserts subtle pause markers at major transitions (`...` or paragraph breaks)
- Expands numbers and abbreviations ("1920s" → "nineteen-twenties", "Dr." → "Doctor")
- Cleans up punctuation that reads awkwardly aloud (nested parentheticals, complex em-dash constructions)
- Flags and smooths anything that trips up TTS (unusual proper nouns get phonetic hints removed before final output)

The original scene text is always preserved. The narration version is a parallel
field used only for TTS input.

**Output:** `narration_text` field populated in `script.json` for each scene.

---

## Context Budget for Long Stories

For stories targeting 60-120 minutes (9,000-18,000 words, 30-60 scenes):

- Scenes are generated in **chapters** of 5-8 scenes
- Within a chapter, the full context accumulates naturally
- Between chapters, the running summary compresses prior events
- The story bible and craft notes are included in every call (non-negotiable for consistency)
- The style reference can be trimmed to the single most representative excerpt for very long stories if context pressure becomes an issue

**Estimated API calls for a 60-minute story (~30 scenes):**
- Phase 1: 1 call (analysis)
- Phase 2: 1 call (story bible)
- Phase 3: 1 call (outline)
- Phase 4: 30 calls (one per scene)
- Phase 5: 30 calls (critique) + ~15 calls (revision, assuming half need it)
- Phase 6: 1-2 calls (image prompts, can batch several scenes per call)
- Phase 7: 1-2 calls (narration prep, can batch)

**Total: ~80 Claude API calls.** At typical costs, this adds ~$2-4 to the story
generation phase. A worthwhile investment for quality.

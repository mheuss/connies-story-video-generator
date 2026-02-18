# Story Video Generator

**Note:** this is a work in progress. It might never be completed if I see something shiny and get distracted.

A Python CLI tool that turns a story into a narrated video for YouTube. You give it text, it gives you a video with AI narration, timed captions, and illustrated scenes.

## Why On Earth?

My wife loves to listen to stories on YouTube. I thought it might be fun for her to have a tool that'd help her create
some of her own. And hey, good excuse for getting more reps in with Python.

## How It Works

The pipeline has three input modes:

- **Original** -- You provide a topic or premise. The AI writes the story from scratch.
- **Inspired by** -- You provide an existing story as inspiration. The AI writes something new that captures similar themes and mood.
- **Adapt** -- You provide a finished story. The AI narrates it word for word and handles structure and visuals.

Each mode feeds into a multi-phase pipeline:

1. **Story writing** -- Claude generates (or structures) the narrative
2. **Narration prep** -- Claude API rewrites text for spoken delivery (abbreviations, numbers, punctuation, pronunciation)
3. **TTS generation** -- OpenAI or ElevenLabs converts text to audio
4. **Image generation** -- GPT Image 1.5 creates a scene illustration per chapter
5. **Caption generation** -- Whisper produces word-level timestamps
6. **Video assembly** -- FFmpeg composites everything into the final video

The pipeline saves state between phases. If something fails, you resume from where it stopped instead of starting over.

## Tech Stack

Python 3.14, Claude API (writing), OpenAI TTS or ElevenLabs v3 (narration), GPT Image 1.5 (illustrations), Whisper (captions), FFmpeg (video). See `pyproject.toml` for the full dependency list.

## Current Status

The adapt and inspired_by flows work end-to-end. You can give it a story and get back a finished video with narration, illustrations, timed captions, and crossfade transitions. The original mode (write from a topic) is not yet implemented.

### What's Working

- **Full adapt pipeline** -- 8 phases run sequentially: scene splitting, narration flagging, image prompts, narration prep, TTS, image generation, caption generation, video assembly
- **Inspired_by creative flow** -- 5 phases: source analysis (craft notes + thematic brief), story bible (characters, setting, rules), outline (scene beats with word targets), scene prose (with running summary), critique/revision (single-pass polish). Feed into the shared media pipeline.
- **LLM-based narration prep** -- Claude API handles abbreviations, numbers, and punctuation contextually instead of brittle regex transforms. Produces a changelog of all modifications.
- **Multi-voice narration** -- YAML front matter defines voice mappings, inline `**voice:name**` tags switch between voices mid-scene. Works with both OpenAI and ElevenLabs.
- **Mood tags** -- inline `**mood:thoughtful**` tags add emotional direction. OpenAI uses its `instructions` parameter; ElevenLabs v3 uses freeform audio tags.
- **Two TTS providers** -- OpenAI (`gpt-4o-mini-tts`) and ElevenLabs (v3). Switch via config file.
- **CLI** -- all five commands functional: `create`, `resume`, `estimate`, `status`, `list`
- **Resume from failure** -- pipeline saves state per phase and per scene, picks up where it left off
- **Semi-automated mode** -- pauses at content phases for human review, or runs straight through in autonomous mode
- **Cost estimation** -- projected costs before starting, actual costs after completion
- **877 tests** covering all modules

### Up Next

- Original input mode -- same creative flow as inspired_by but with topic/premise input instead of source material

### Pie in the Sky

- Inline image tags -- author-controlled image transitions within scenes
- Pause tags -- precise silence injection for pacing and poetry
- Background music / sound effects -- audio overlay with volume and duration control
- Iterative critique/revision -- critic and author personas with multi-pass refinement
- User-configurable story length -- `--target-words`, `--target-scenes` flags
- Web UI
- Story translation

## Usage

```
pip install -e ".[dev]"
```

You'll need FFmpeg installed on your system and API keys in a `.env` file:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...          # optional, only if using ElevenLabs TTS
```

### Multi-Voice Stories

Add a YAML header to your story file to define voice mappings and use inline tags to switch between them:

```
---
voices:
  narrator: nova
  old_man: echo
default_voice: narrator
---
The old man sat alone. **voice:old_man** **mood:dry** "Black or white?"
**voice:narrator** The boy pointed at the black pieces.
```

Voice IDs depend on your TTS provider. OpenAI uses names like `nova`, `echo`, `alloy`. ElevenLabs uses voice ID hashes from your account.

### ElevenLabs

To use ElevenLabs instead of OpenAI for TTS, create a config file:

```yaml
tts:
  provider: elevenlabs
  model: eleven_v3
  output_format: mp3_44100_128
```

Then pass it with `--config`:

```
story-video create --mode adapt --source story.txt --config config_elevenlabs.yaml
```

### Commands

```
story-video create --mode adapt --source story.txt   # adapt an existing story into a video
story-video create --mode inspired_by --source story.txt           # new story inspired by the source
story-video create --mode inspired_by --source story.txt --premise "set it in space"  # with creative direction
story-video create --mode adapt --source story.txt --autonomous  # skip review checkpoints
story-video create --mode adapt --source story.txt --verbose     # enable debug logging
story-video resume                                    # continue the most recent project
story-video resume --project-id <id>                  # continue a specific project
story-video estimate --mode adapt --source story.txt  # show cost estimate without starting
story-video status --project-id <id>                  # show current state of a project
story-video list                                      # list all projects
```

## Development

```
pytest                       # run all tests
pytest -m "not slow"         # skip tests that make real API calls
ruff format                  # format code
ruff check                   # lint
```

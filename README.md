# Story Video Generator

**Note:** this is a work in progress. It might never be completed if I see something shiny and get distracted.

A Python CLI tool that turns a topic, inspiration, or existing story into a narrated video for YouTube. You give it text,
it gives you a 30-120 minute video with AI narration, timed captions, and illustrated scenes.

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
2. **Narration prep** -- Text is optimized for spoken delivery
3. **TTS generation** -- OpenAI converts text to audio
4. **Image generation** -- GPT Image 1.5 creates a scene illustration per chapter
5. **Caption generation** -- Whisper produces word-level timestamps
6. **Video assembly** -- FFmpeg composites everything into the final video

The pipeline saves state between phases. If something fails, you resume from where it stopped instead of starting over.

## Tech Stack

Python 3.11+, Claude API (writing), OpenAI TTS / GPT Image 1.5 / Whisper (media), FFmpeg (video). See `pyproject.toml` for the full dependency list.

## Current Status

The adapt flow works end-to-end. You can give it a story and get back a finished video with narration, illustrations, timed captions, and crossfade transitions. The creative flow (original/inspired_by modes) is not yet implemented.

### What's Working

- **Full adapt pipeline** -- 8 phases run sequentially: scene splitting, narration flagging, image prompts, narration prep, TTS, image generation, caption generation, video assembly
- **CLI** -- all five commands functional: `create`, `resume`, `estimate`, `status`, `list`
- **Resume from failure** -- pipeline saves state per phase and per scene, picks up where it left off
- **Semi-automated mode** -- pauses at content phases for human review, or runs straight through in autonomous mode
- **Cost estimation** -- projected costs before starting, actual costs after completion
- **678 tests** covering all modules

### Up Next

- Story writer (creative flow) -- analysis, story bible, outline, prose, critique/revision
- Original and inspired_by input modes

### Pie in the Sky

- Web UI -- interactive story creation and management
- ElevenLabs TTS provider option
- Story translation

## Usage

```
pip install -e ".[dev]"
```

You'll need FFmpeg installed on your system and API keys for Anthropic and OpenAI in a `.env` file:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### Commands

```
story-video create --mode adapt --source story.txt   # adapt an existing story into a video
story-video create --mode adapt --source story.txt --autonomous  # skip review checkpoints
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

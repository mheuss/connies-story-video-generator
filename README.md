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
4. **Image generation** -- DALL-E 3 creates a scene illustration per chapter
5. **Caption generation** -- Whisper produces word-level timestamps
6. **Video assembly** -- FFmpeg composites everything into the final video

The pipeline saves state between phases. If something fails, you resume from where it stopped instead of starting over.

## Tech Stack

Python 3.11+, Claude API (writing), OpenAI TTS / DALL-E 3 / Whisper (media), FFmpeg (video). See `pyproject.toml` for the full dependency list.

## Development Roadmap

The project is being built bottom-up: data layer first, then pipeline components, then orchestration, then CLI.

### Completed

- Data models (Pydantic v2) -- enums, config, scene/project models
- Configuration loading -- three-way merge (defaults < config.yaml < CLI overrides)
- Project state management -- creation, persistence, phase transitions, resume logic
- Text utilities -- abbreviation expansion, number-to-words, pause markers, TTS prep
- Retry infrastructure -- exponential backoff with tenacity
- Cost estimation -- per-service rate calculations with projected and actual modes
- Claude API client -- text generation, structured output, transient error retry
- Story writer (adapt flow) -- scene splitting with text preservation, narration flagging
- TTS generator -- OpenAI provider with retry and provider abstraction
- Image generator -- DALL-E 3 provider with provider abstraction
- Caption generator -- Whisper provider with word and segment timestamps
- Test suite -- 483 tests covering all completed modules

### Up Next

- Story writer (creative flow) -- analysis, story bible, outline, prose, critique/revision
- FFmpeg module -- command building, Ken Burns effect, blur backgrounds, crossfade transitions, subtitle rendering
- Video assembler -- per-scene segment rendering and final concatenation
- Pipeline orchestrator -- phase sequencing, state management, checkpoint pausing
- CLI -- all commands fully functional (create, resume, estimate, status, list)

### Pie in the Sky

- Web UI -- interactive story creation and management
- AI-assisted story editing
- Story translation
- Collaborative editing

## Usage

```
pip install -e ".[dev]"
```

Commands (not yet functional):

```
story-video create    -- start a new project
story-video resume    -- continue a paused/failed project
story-video estimate  -- show cost estimate without starting
story-video status    -- show current state of a project
story-video list      -- list all projects
```

Requires FFmpeg installed on your system and API keys for Anthropic and OpenAI in a `.env` file.

## Development

```
pytest                       # run all tests
pytest -m "not slow"         # skip tests that make real API calls
ruff format                  # format code
ruff check                   # lint
```
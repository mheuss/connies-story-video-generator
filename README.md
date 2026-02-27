# Story Video Generator

Turn a story into a narrated video for YouTube. Give it text, get back a video with AI narration, timed captions, and illustrated scenes. Use the CLI for scripted workflows or the web UI for a guided experience.

## Why On Earth?

My wife loves to listen to stories on YouTube. I thought it might be fun for her to have a tool that'd help her create
some of her own. And hey, good excuse for getting more reps in with Python.

## How It Works

The pipeline has three input modes:

- **Original** -- You provide a topic or premise. The AI writes the story from scratch.
- **Inspired by** -- You provide an existing story as inspiration. The AI writes something new that captures similar themes and mood.
- **Adapt** -- You provide a finished story. The AI narrates it word for word and handles structure and visuals.

### Creative Flow (Original & Inspired By)

Original and inspired_by share the same 11-phase pipeline. The difference is the input: original takes a topic or premise, inspired_by takes a source story. Both go through analysis, story bible, outline, prose, critique, then into the shared media pipeline.

![Creative Flow](docs/diagrams/creative-flow.png)

### Adapt Flow

Adapt mode skips the authoring phases (story bible, outline, prose, critique). It analyzes the source text, splits it into scenes, flags narration issues, then feeds into the shared media pipeline.

![Adapt Flow](docs/diagrams/adapt-flow.png)

### Resume

The pipeline saves state between phases. If something fails, you resume from where it stopped instead of starting over.

## Tech Stack

Python 3.11+, Claude API (writing), OpenAI TTS or ElevenLabs v3 (narration), GPT Image 1.5 (illustrations), Whisper (captions), FFmpeg (video), React + Vite (web UI). See `pyproject.toml` for the full dependency list.

## Features

- **Full adapt pipeline** -- 9 phases run sequentially: analysis, scene splitting, narration flagging, image prompts, narration prep, TTS, image generation, caption generation, video assembly
- **Original creative flow** -- Provide a topic, premise, or detailed brief. The AI interprets your creative direction, builds characters and setting, outlines the story, writes prose, and revises it before handing off to the media pipeline.
- **Inspired_by creative flow** -- 5 authoring phases: source analysis, story bible, outline, scene prose, critique/revision. Then into the shared media pipeline.
- **Web UI** -- Browser-based interface for creating projects, monitoring progress with live updates, reviewing and editing artifacts at checkpoints, and downloading the finished video. Run `story-video serve` to start it.
- **CLI** -- Six commands: `create`, `resume`, `estimate`, `status`, `list`, `serve`
- **Checkpoint review** -- Pipeline pauses at editorial phases so you can review and edit artifacts before continuing. Available in both CLI (semi-auto mode) and web UI. Or run in autonomous mode to skip checkpoints entirely.
- **LLM-based narration prep** -- Claude API handles abbreviations, numbers, and punctuation contextually instead of brittle regex transforms. Produces a changelog of all modifications.
- **Multi-voice narration** -- YAML front matter defines voice mappings, inline `**voice:name**` tags switch between voices mid-scene. Works with both OpenAI and ElevenLabs.
- **Mood tags** -- inline `**mood:thoughtful**` tags add emotional direction. OpenAI uses its `instructions` parameter; ElevenLabs v3 uses freeform audio tags.
- **Pause tags** -- inline `**pause:1.5**` tags insert silence into narration audio. Useful for pacing, dramatic beats, and poetry.
- **Scene markers** -- `**scene:Title**` tags in your story file let you pre-split scenes. The pipeline auto-detects them and skips the AI splitting step.
- **Two TTS providers** -- OpenAI (`gpt-4o-mini-tts`) and ElevenLabs (v3). Switch via config file.
- **Inline image tags** -- `**image:key**` tags in your story text reference image prompts defined in the YAML header. Control exactly when images change within a scene, independent of scene boundaries.
- **Background music** -- `**music:key**` tags trigger audio tracks defined in the YAML header. Supports volume, looping, fade in/out. Audio is mixed with narration using FFmpeg's amix filter, timed to caption word offsets.
- **Resume from failure** -- pipeline saves state per phase and per scene, picks up where it left off
- **Cost estimation** -- projected costs before starting, actual costs after completion
- **Lead-in silence** -- configurable delay before narration starts, giving the opening image time to fade in from black
- **935+ tests** covering all modules (backend and frontend)

### Pie in the Sky

- Iterative critique/revision -- critic and author personas with multi-pass refinement
- User-configurable story length -- `--target-words`, `--target-scenes` flags
- Story translation
- TTS audio preview -- listen to narration per scene at checkpoints before committing to video assembly
- Project browser -- list existing projects on the home screen, select one, and resume from any completed phase
- Phase navigation -- go back to an earlier pipeline phase and re-run from there, enabling iterative refinement
- Docker packaging -- Dockerfile, static file serving, port config
- File upload -- upload a story file instead of pasting text

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

### Web UI

Start the web server:

```
story-video serve
```

Open `http://localhost:8000` in your browser. The web UI lets you:

- Enter API keys on first run (saved to `.env`)
- Create a new project by choosing a mode and pasting your story text
- Watch progress in real time with animated progress bars
- Review and edit artifacts at each checkpoint
- Auto-approve remaining checkpoints with one click
- Watch and download the finished video

### CLI Commands

```
story-video create --mode adapt --input story.txt                         # adapt an existing story
story-video create --mode original --input "A love story set in 1920s Paris"  # AI writes from a brief
story-video create --mode inspired_by --input story.txt                   # new story inspired by source
story-video create --mode inspired_by --input story.txt --premise "..."   # with creative direction
story-video create --mode adapt --input story.txt --autonomous            # skip review checkpoints
story-video resume                                    # continue the most recent project
story-video resume <project-id>                       # continue a specific project
story-video estimate --mode adapt                     # show cost estimate without starting
story-video status <project-id>                       # show current state of a project
story-video list                                      # list all projects
story-video serve                                     # start the web UI
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

Use `**pause:N**` tags to insert silence (in seconds) for pacing:

```
The door swung open. **pause:1.5** "Is anyone there?" she whispered.
```

### Scene Markers

If you want to control where scenes split, add `**scene:Title**` tags to your story file:

```
**scene:The Storm**
It was a dark and stormy night. The wind howled through the trees.

**scene:The Journey**
The hero ventured forth bravely into the unknown.
```

When the pipeline detects scene tags, it splits on them directly and skips the AI scene-splitting step. Any text before the first tag becomes a scene titled "Opening".

### Inline Image Tags

Define image prompts in the YAML header and place `**image:key**` tags in your story text to control when images change:

```
---
voices:
  narrator: nova
images:
  lighthouse:
    prompt: A weathered stone lighthouse on a rocky cliff at sunset
  storm:
    prompt: Dark storm clouds rolling over a turbulent ocean
---
**image:lighthouse** The old keeper climbed the spiral stairs as he had every evening
for thirty years. **image:storm** But tonight the horizon looked different.
```

Each image displays from its tag position until the next tag (or end of scene). The pipeline maps tag positions to audio timestamps using Whisper captions, so image transitions sync with the narration.

### Background Music

Define audio assets in the YAML header and use `**music:key**` tags to trigger them:

```
---
voices:
  narrator: nova
audio:
  rain:
    file: sounds/rain.mp3
    volume: 0.2
    loop: true
    fade_in: 2.0
    fade_out: 3.0
  thunder:
    file: sounds/thunder.mp3
    volume: 0.5
---
**music:rain** The rain began to fall. **music:thunder** A crack of thunder
split the sky.
```

Audio files are paths relative to your project directory. Each track supports `volume` (0-1, default 1.0), `loop` (default false), `fade_in` and `fade_out` (seconds, default 0). Music is scoped per scene and mixed with narration via FFmpeg.

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
story-video create --mode adapt --input story.txt --config config_elevenlabs.yaml
```

## Development

```
pytest                       # run all tests
pytest -m "not slow"         # skip tests that make real API calls
ruff format                  # format code
ruff check                   # lint
cd web && npm test           # run frontend tests
```

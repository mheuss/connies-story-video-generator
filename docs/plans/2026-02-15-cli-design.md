# CLI Implementation Design

## Scope

Implement the 5 CLI commands (create, resume, estimate, status, list) as a thin wiring layer over existing modules. Adapt mode only — creative flow commands are out of scope until those pipeline modules exist.

## Architecture

The CLI is a wiring layer. It parses user input, loads config, creates/loads state, instantiates providers, and delegates to existing modules. No business logic lives here.

**Five commands, two categories:**

| Category | Commands | What they do |
|----------|----------|-------------|
| Pipeline | `create`, `resume` | Run the orchestrator |
| Read-only | `estimate`, `status`, `list` | Query state/config, display output |

**Dependencies flow one way:** CLI -> config -> state -> orchestrator -> pipeline modules. The CLI never calls pipeline modules directly.

**New dependency:** `rich` for terminal output (tables, colors, panels).

## Commands

### `create`

```
story-video create \
  --mode adapt \
  --source-material path/to/story.txt \
  --style-reference path/to/style_sample.txt \
  --duration 30 \
  --voice nova \
  --autonomous \
  --output-dir ./output \
  --config ./config.yaml
```

**Flow:**
1. Parse flags, validate mode-specific requirements
2. Load config: `load_config(config_path, cli_overrides)` — CLI flags become overrides
3. Read source material / topic from file if path exists, else treat as inline text
4. Generate project ID: `{mode}-{YYYY-MM-DD}` with numeric suffix on collision
5. Create state: `ProjectState.create(project_id, mode, config, output_dir)`
6. Store source text on state
7. Instantiate providers inline (ClaudeClient, OpenAITTSProvider, etc.)
8. Call `run_pipeline(state, ...)`
9. Display outcome based on `state.metadata.status`

**Flags:**

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--mode` | Yes | -- | `original`, `inspired_by`, or `adapt` |
| `--topic` | For `original` | -- | Premise (string or path to file) |
| `--source-material` | For `adapt`, `inspired_by` | -- | Source story (string or path to file) |
| `--style-reference` | No | -- | Path to style sample prose |
| `--duration` | No | 30 | Target duration in minutes |
| `--voice` | No | From config | OpenAI TTS voice name |
| `--autonomous` | No | false | Skip human review checkpoints |
| `--output-dir` | No | `./output` | Where projects are stored |
| `--config` | No | `./config.yaml` | Path to config file |

**Validation:**
- `original` requires `--topic`
- `adapt` and `inspired_by` require `--source-material`
- `--source-material` path must exist if provided as a path

**CLI overrides mapping:**
- `--voice nova` -> `{"tts.voice": "nova"}`
- `--duration 30` -> `{"story.target_duration_minutes": 30}`
- `--autonomous` -> `{"pipeline.autonomous": True}`

### `resume`

```
story-video resume [PROJECT_ID]
```

1. If `project_id` given -> `ProjectState.load(output_dir / project_id)`
2. If no `project_id` -> scan `output_dir` for most recent project (by `created_at`)
3. Instantiate providers inline
4. Call `run_pipeline(state, ...)` — orchestrator resume logic handles the rest
5. Display outcome based on `state.metadata.status`

### `estimate`

Same flags as `create` (mode, duration, voice, etc.) but does NOT create a project.

1. Build config from flags
2. Call `estimate_cost(mode, config)` for projected costs
3. Display via Rich panel wrapping `format_cost_estimate()`

### `status`

```
story-video status [PROJECT_ID]
```

1. If `project_id` given -> load that project
2. If no `project_id` -> most recent project
3. Display Rich table with:
   - Project metadata (ID, mode, phase, status, created)
   - Per-scene asset status grid (scene number x asset type, color-coded)

### `list`

1. Scan `output_dir` for all subdirectories containing `project.json`
2. Load metadata from each (lightweight JSON parse)
3. Display Rich table: project ID, mode, current phase, status, created date
4. Sorted by creation date (newest first)

## Provider Instantiation

Inline in CLI commands. `create` and `resume` instantiate providers directly:

```python
claude_client = ClaudeClient()
tts_provider = OpenAITTSProvider()
image_provider = OpenAIImageProvider()
caption_provider = OpenAIWhisperProvider()

run_pipeline(state, claude_client=claude_client, tts_provider=tts_provider, ...)
```

## Project ID Generation

Auto-generated as `{mode}-{YYYY-MM-DD}`. On collision, append numeric suffix: `adapt-2026-02-15`, `adapt-2026-02-15-2`, `adapt-2026-02-15-3`.

## Output Formatting

Rich library for all terminal output:
- **Tables** for status and list commands (color-coded status cells)
- **Panels** for success/error/info messages after pipeline runs
- **Existing `format_cost_estimate()`** wrapped in Rich panel (no rewrite of cost.py)

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Pipeline completes | Success panel: "Pipeline complete! Video at {path}" |
| Pipeline pauses (semi-auto) | Info panel: "Paused at {phase} for review. Run `story-video resume` to continue." |
| Pipeline fails | Error panel: "Failed at {phase}. Run `story-video resume` to retry." + exception message |
| Missing API key | Clear message: "Missing ANTHROPIC_API_KEY environment variable." |
| No projects found | "No projects found in {output_dir}." |
| Invalid project ID | "Project '{id}' not found in {output_dir}." |
| Source file not found | Typer validation error before pipeline starts |

## Shared Helpers

`_find_most_recent_project(output_dir) -> Path | None` — scans output_dir for project.json files, returns path to most recent by `created_at`. Used by `resume` and `status`.

`_generate_project_id(mode, output_dir) -> str` — generates collision-safe project ID.

`_read_text_input(value) -> str` — if value is a path to existing file, reads it; otherwise returns as-is.

`_display_outcome(state) -> None` — checks `state.metadata.status` and shows appropriate Rich panel.

## Testing Strategy

Test at the Typer invocation level using `typer.testing.CliRunner`. Mock at provider constructors and `run_pipeline`.

| Category | Tests |
|----------|-------|
| create — happy path | State created, `run_pipeline` called, output shown |
| create — validation | `adapt` without `--source-material` fails, `original` without `--topic` fails |
| create — source reading | File path reads content, string treated as inline |
| create — config overrides | `--voice`, `--duration`, `--autonomous` flow to config |
| create — project ID | Auto-generated, collision-suffixed |
| resume — with ID | Loads correct project, calls `run_pipeline` |
| resume — no ID | Finds most recent project |
| resume — no projects | Clean error message |
| estimate | Calls `estimate_cost`, displays output, no project created |
| status | Loads project, displays phase + asset table |
| list | Scans output dir, shows all projects |
| list — empty | Clean message |
| error display | Pipeline exception -> error panel, clean exit code |

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Provider instantiation | Inline in CLI | Simple, no abstraction, matches project style |
| Output formatting | Rich library | Tables, colors, panels — worth the dependency |
| Project ID format | `{mode}-{YYYY-MM-DD}[-N]` | Readable, sortable, collision-safe |
| Source material input | String or file auto-detect | Path exists -> read file, else inline text |
| Config override mapping | CLI flags -> dict keys | Feeds into existing `load_config(cli_overrides=...)` |
| Testing approach | `CliRunner` + mocked providers | Full wiring tested, no real API calls |
| Cost display | Rich panel wrapping `format_cost_estimate()` | Reuses cost.py |
| Most recent project | Scan output_dir, sort by `created_at` | Shared helper |
| Scope | Adapt mode only | Creative flow modules not implemented yet |
| Error display | Rich error panels, no stack traces | Verbose mode deferred (YAGNI) |

## Out of Scope

- Creative flow commands (original/inspired_by) — pipeline modules not implemented
- Progress bars during pipeline execution — needs orchestrator callback hooks
- `--verbose` flag — YAGNI for MVP

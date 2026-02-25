# Web UI Design

**Status:** Approved

**Goal:** Make the story-video pipeline accessible to non-technical users through a browser-based interface. Success criteria: a non-technical user can create a video end-to-end without touching a terminal.

**Approach:** Monorepo with FastAPI backend + React SPA frontend, single Docker container, localhost-only deployment.

---

## 1. High-Level Architecture

**Backend** (`src/story_video/web/`): FastAPI app that wraps the existing pipeline. Three route groups: Project (CRUD), Artifact (serve/edit checkpoint files), Pipeline (start/approve/progress). The pipeline runs in a background thread; progress streams to the frontend via SSE.

**Frontend** (`web/`): React SPA with three screen groups:
- **Create** — Choose mode, upload/paste source material, start the pipeline.
- **Review/Edit** — View artifacts at each checkpoint, edit in-browser, approve to continue.
- **Progress** — Per-scene progress bar during media generation phases.

**Serving:** FastAPI serves the React build as static files. Single process, single port.

---

## 2. User Flow

1. User opens `http://localhost:8033` (port configurable, default 8033).
2. **Create screen:** Pick a mode (adapt/original/inspired-by), paste text or upload a file. Click "Create."
3. Pipeline starts. **Progress screen** shows current phase and per-scene progress bars during media generation.
4. Pipeline hits a checkpoint. **Review screen** shows artifacts for that phase:
   - Outline phase: story outline text.
   - Narration phase: narration segments, one per scene.
   - Image generation: generated images with their prompts.
   - Audio/TTS: audio playback per scene.
5. User reviews, optionally edits inline, clicks "Approve & Continue."
6. Steps 3-5 repeat for each editorial phase (9 checkpoint phases total in semi-auto mode).
7. Final video ready. User previews in-browser and downloads.

---

## 3. API Design

All routes under `/api/v1/`.

### Project routes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/projects` | Create project. Body: `{ mode, source_text?, source_file? }`. Returns `{ project_id, project_dir }`. |
| `GET` | `/projects/{id}` | Project status, current phase, scene count, config. |
| `DELETE` | `/projects/{id}` | Cancel and clean up. |

### Pipeline routes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/projects/{id}/start` | Start pipeline (returns immediately, runs in background thread). |
| `POST` | `/projects/{id}/approve` | Approve checkpoint, continue to next phase. |
| `GET` | `/projects/{id}/progress` | SSE endpoint streaming progress events. |

### SSE event types

- `phase_started { phase, scene_count }` — New phase began.
- `scene_progress { phase, scene_number, total, status }` — Per-scene update during media generation.
- `checkpoint { phase, artifacts[] }` — Pipeline paused, user review needed.
- `completed { video_path }` — Final video ready.
- `error { message, phase?, scene? }` — Something failed.

### Artifact routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects/{id}/artifacts/{phase}` | List artifacts for a checkpoint. |
| `GET` | `/projects/{id}/artifacts/{phase}/{filename}` | Serve a specific file (image, audio, video). |
| `PUT` | `/projects/{id}/artifacts/{phase}/{filename}` | Update an artifact (edited text, regen request). |

### Key decisions

- **SSE over WebSockets.** Simpler, one-directional (server to client). All client-to-server communication is REST.
- **Background thread, not subprocess.** The pipeline already runs in-process. Wrap `run_pipeline()` in a thread, capture progress via callback.
- **Artifact serving is static file serving** from the project directory. No database.
- **All state on disk** in the existing `ProjectState` JSON. No additional persistence layer.

---

## 4. Data Flow & State Management

### Backend — no database, just files

The pipeline persists everything via `ProjectState` (JSON metadata + file assets). The web backend reads and writes the same state. A project started via CLI can be inspected via web UI and vice versa. No migration, no ORM, no database.

The "active project" is just a path held in memory by the server process.

### Pipeline-to-frontend progress bridge

1. Wrap `run_pipeline()` in a background thread.
2. Pass a progress callback that pushes events to an `asyncio.Queue`.
3. The SSE endpoint reads from the queue and yields events to the client.

The pipeline code stays untouched. The callback is the only integration point.

### Frontend — minimal React state

- **Server state** (project status, artifacts, progress) fetched via REST + SSE. Lightweight fetch wrapper, no Redux or query library for v1.
- **UI state** (panel visibility, form inputs) in component state.
- `EventSource` opens when user navigates to a project, closes on unmount.

### Artifact editing flow

1. User clicks "Edit" on an artifact.
2. Frontend fetches content via `GET /artifacts/{phase}/{filename}`.
3. User edits in a textarea.
4. On save, `PUT /artifacts/{phase}/{filename}` writes to disk.
5. "Approve & Continue" calls `POST /approve` to resume the pipeline.

No draft/publish distinction. Edits go straight to disk, same as CLI semi-auto mode.

---

## 5. Error Handling & Edge Cases

### Pipeline failures

Pipeline raises typed exceptions (`FFmpegError`, etc.). The background thread catches these, pushes an `error` SSE event, and sets project status to `failed`. Frontend shows the error with a "Retry" button that calls `POST /start` to resume from the failed phase (orchestrator already supports resumption).

### Connection drops

SSE auto-reconnects via `EventSource`. On reconnect, client fetches `GET /projects/{id}` to sync, then resumes listening. If the server restarts mid-pipeline, the project stays in its last persisted state. User hits "Retry" to resume.

### File validation

Source material upload: reject over 10MB, validate readable text. Artifact edits: non-empty text. The pipeline validates content when it processes it.

### Concurrent access

Single-user, one project at a time. No locking. Starting a second pipeline while one runs returns 409 Conflict.

### API key handling

On startup, if `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` are missing, the UI shows a setup form. User enters keys, backend writes to `.env`, loads into environment. No restart needed. If keys fail mid-pipeline, the error hints to check keys. A Settings page reuses the same form for updates.

---

## 6. Docker & Deployment

### Single container

- **Base image:** Python 3.12 slim.
- **FFmpeg:** Installed via apt.
- **Python deps:** Installed via pip.
- **React frontend:** Built at image build time (`npm run build`), served via FastAPI `StaticFiles` mount.
- **One process:** `uvicorn story_video.web.app:app --host 0.0.0.0 --port 8033`.

### Run command

```bash
docker run -p 8033:8033 -v ./projects:/data -v ./.env:/app/.env story-video
```

- `./projects:/data` — Project directories persist on host.
- `./.env:/app/.env` — API keys via volume mount (or entered via setup form on first run).

### Port configuration

- Default: 8033.
- Override: `PORT=9000` environment variable or `--port 9000` CLI flag.
- React reads port from its serving origin (same-origin), no rebuild needed.

### Non-Docker usage

```bash
pip install -e ".[web]"
python -m story_video serve
```

Everything works the same without container isolation. No Docker Compose for v1.

---

## 7. Testing Strategy

### Backend (Python, pytest)

- **Unit tests** for route handlers — mock the pipeline, verify request/response shapes, status codes, errors.
- **Integration tests** for the progress bridge — verify pipeline events flow through queue to SSE output. Use FastAPI `TestClient`.
- **No end-to-end pipeline tests in web layer.** Pipeline is already tested. Web tests verify correct wrapping and delegation.

### Frontend (React, Vitest + React Testing Library)

- **Component tests** — screens render correctly, buttons trigger API calls, SSE events update UI.
- **No Cypress/Playwright for v1.** Component tests plus manual testing cover it. Add E2E when UI stabilizes.

### Not tested

- Docker build (manual, CI smoke test later).
- Visual styling (manual).
- Real API key validation (requires live calls).

### Test organization

```
tests/
  test_web_api.py          # Route handler unit tests
  test_web_progress.py     # SSE progress bridge tests
  test_web_artifacts.py    # Artifact serving/editing tests
web/
  src/__tests__/           # React component tests
```

---

## Scope Summary (v1)

**In scope:**
- Create flow (all three modes), file upload, text paste.
- Checkpoint review with in-browser editing.
- Per-scene progress bars.
- In-browser video preview and download.
- API key setup form.
- Single Docker container.
- Configurable port (default 8033).

**Deferred:**
- YAML tag editing UI (inline image tags, background music tags).
- Multiple concurrent projects.
- User accounts / auth.
- Remote deployment / HTTPS.
- Cypress/Playwright E2E tests.

# Web UI Backend API Implementation Plan (Plan 1 of 3)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a FastAPI backend that wraps the existing pipeline, providing REST endpoints and SSE progress streaming — testable without any frontend.

**Architecture:** New `src/story_video/web/` package with FastAPI app. Routes delegate to `ProjectState` and `run_pipeline()`. The pipeline runs in a background thread; progress events flow through an `asyncio.Queue` to an SSE endpoint. All state lives on disk via the existing `ProjectState` JSON — no database.

**Tech Stack:** FastAPI, uvicorn, python-dotenv, httpx (for async test client), sse-starlette (for SSE streaming)

**Design doc:** `docs/plans/2026-02-25-web-ui-design.md`

---

## Context for the implementer

### Key files you'll interact with

| File | Purpose | Key exports |
|------|---------|-------------|
| `src/story_video/state.py` | Project lifecycle + persistence via `project.json` | `ProjectState` (create, load, save, start_phase, complete_phase, await_review, fail_phase, get_next_phase, get_scenes_for_processing) |
| `src/story_video/models.py` | All Pydantic data models | `InputMode`, `PipelinePhase`, `PhaseStatus`, `AppConfig`, `ProjectMetadata`, `Scene`, `SceneStatus` |
| `src/story_video/pipeline/orchestrator.py` | Pipeline driver | `run_pipeline(state, *, claude_client, tts_provider, image_provider, caption_provider)` |
| `src/story_video/cli.py` | Current CLI (reference for provider instantiation) | `_run_with_providers(state)`, `_make_tts_provider(name)` |
| `src/story_video/config.py` | YAML config loading with 3-way merge | `load_config(path)` |

### How the pipeline works (what you're wrapping)

1. `ProjectState.create(project_id, mode, config, output_dir)` creates a project directory with `project.json`.
2. `run_pipeline(state, ...)` runs phases sequentially. In semi-auto mode (`config.pipeline.autonomous = False`), it pauses at checkpoint phases by calling `state.await_review()` and returning.
3. To resume after a checkpoint, call `run_pipeline(state, ...)` again — `_determine_start_phase()` sees `AWAITING_REVIEW` and advances to the next phase.
4. Provider instantiation: see `cli.py:_run_with_providers()` — creates `ClaudeClient()`, `OpenAIImageProvider()`, `OpenAIWhisperProvider()`, and `_make_tts_provider(config.tts.provider)`.

### Conventions

- TDD: write failing test first, then implement.
- Match existing code style: type hints, docstrings, `__all__` exports.
- Tests go in `tests/` at project root. Test files: `test_web_*.py`.
- Run tests: `pytest tests/test_web_*.py -v`
- Run all tests: `pytest`
- Format: `ruff format`, Lint: `ruff check`

---

## Task 1: Add web dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add the `web` optional dependency group**

Add after the existing `dev` group in `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.0",
    "ruff>=0.5.0",
]
web = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "python-dotenv>=1.0.0",
    "sse-starlette>=2.0.0",
    "httpx>=0.28.0",
]
```

**Step 2: Install**

Run: `pip install -e ".[dev,web]"`
Expected: All packages install successfully.

**Step 3: Verify import**

Run: `python -c "import fastapi; import uvicorn; import sse_starlette; import dotenv; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add web optional dependency group (FastAPI, uvicorn, SSE)"
```

---

## Task 2: Create web package skeleton with health endpoint

**Files:**
- Create: `src/story_video/web/__init__.py`
- Create: `src/story_video/web/app.py`
- Create: `tests/test_web_app.py`

**Step 1: Write the failing test**

```python
"""Tests for story_video.web.app — FastAPI application setup."""

from fastapi.testclient import TestClient

from story_video.web.app import create_app


class TestAppSetup:
    """Application factory and health endpoint."""

    def test_health_endpoint(self):
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_app_has_api_v1_prefix(self):
        app = create_app()
        client = TestClient(app)
        # Non-prefixed path should 404
        response = client.get("/health")
        assert response.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_app.py -v`
Expected: FAIL (cannot import `story_video.web.app`)

**Step 3: Write minimal implementation**

`src/story_video/web/__init__.py`:
```python
"""Web API for the Story Video Generator."""
```

`src/story_video/web/app.py`:
```python
"""FastAPI application factory.

Creates and configures the FastAPI app with all route groups
mounted under the /api/v1 prefix.
"""

from fastapi import APIRouter, FastAPI

__all__ = ["create_app"]

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance with all routes mounted.
    """
    app = FastAPI(title="Story Video", version="0.1.0")
    app.include_router(router)
    return app
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_app.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add src/story_video/web/__init__.py src/story_video/web/app.py tests/test_web_app.py
git commit -m "feat(web): add FastAPI app skeleton with health endpoint"
```

---

## Task 3: API key setup endpoint

**Files:**
- Create: `src/story_video/web/routes_settings.py`
- Create: `tests/test_web_settings.py`
- Modify: `src/story_video/web/app.py`

**Step 1: Write the failing tests**

```python
"""Tests for story_video.web.routes_settings — API key management."""

import os

from fastapi.testclient import TestClient

from story_video.web.app import create_app


class TestGetApiKeyStatus:
    """GET /api/v1/settings/api-keys returns which keys are configured."""

    def test_returns_key_status_when_both_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/settings/api-keys")
        assert response.status_code == 200
        data = response.json()
        assert data["anthropic_configured"] is True
        assert data["openai_configured"] is True

    def test_returns_false_when_keys_missing(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        app = create_app()
        client = TestClient(app)
        response = client.get("/api/v1/settings/api-keys")
        assert response.status_code == 200
        data = response.json()
        assert data["anthropic_configured"] is False
        assert data["openai_configured"] is False


class TestSetApiKeys:
    """POST /api/v1/settings/api-keys writes keys to .env and loads them."""

    def test_sets_keys_and_writes_env_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        env_path = tmp_path / ".env"
        app = create_app(env_path=env_path)
        client = TestClient(app)
        response = client.post(
            "/api/v1/settings/api-keys",
            json={
                "anthropic_api_key": "sk-ant-new",
                "openai_api_key": "sk-new",
            },
        )
        assert response.status_code == 200
        # Keys are now in environment
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-new"
        assert os.environ.get("OPENAI_API_KEY") == "sk-new"
        # .env file was written
        assert env_path.exists()
        content = env_path.read_text()
        assert "ANTHROPIC_API_KEY=sk-ant-new" in content
        assert "OPENAI_API_KEY=sk-new" in content

    def test_partial_update_preserves_existing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-existing")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        env_path = tmp_path / ".env"
        app = create_app(env_path=env_path)
        client = TestClient(app)
        response = client.post(
            "/api/v1/settings/api-keys",
            json={"openai_api_key": "sk-new"},
        )
        assert response.status_code == 200
        # Existing key preserved
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-existing"
        # New key set
        assert os.environ.get("OPENAI_API_KEY") == "sk-new"

    def test_rejects_empty_key_values(self, tmp_path):
        env_path = tmp_path / ".env"
        app = create_app(env_path=env_path)
        client = TestClient(app)
        response = client.post(
            "/api/v1/settings/api-keys",
            json={"anthropic_api_key": "  "},
        )
        assert response.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_settings.py -v`
Expected: FAIL (cannot import `routes_settings`)

**Step 3: Write minimal implementation**

`src/story_video/web/routes_settings.py`:
```python
"""Settings routes — API key management.

Provides endpoints to check API key status and set/update keys.
Keys are written to a .env file and loaded into the process environment.
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# Set by create_app() — path to .env file for key persistence.
_env_path: Path = Path(".env")


def configure(env_path: Path) -> None:
    """Set the .env file path. Called by create_app()."""
    global _env_path  # noqa: PLW0603
    _env_path = env_path


@router.get("/api-keys")
async def get_api_key_status() -> dict:
    """Check which API keys are configured in the environment."""
    return {
        "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()),
        "openai_configured": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
    }


class ApiKeyUpdate(BaseModel):
    """Request body for updating API keys."""

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    @field_validator("anthropic_api_key", "openai_api_key", mode="before")
    @classmethod
    def reject_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            msg = "Key value must not be blank"
            raise ValueError(msg)
        return v


@router.post("/api-keys")
async def set_api_keys(body: ApiKeyUpdate) -> dict:
    """Set or update API keys.

    Writes keys to the .env file and loads them into the process
    environment so the pipeline can use them immediately.
    """
    if body.anthropic_api_key is None and body.openai_api_key is None:
        raise HTTPException(status_code=422, detail="At least one key must be provided")

    # Update environment
    if body.anthropic_api_key is not None:
        os.environ["ANTHROPIC_API_KEY"] = body.anthropic_api_key
    if body.openai_api_key is not None:
        os.environ["OPENAI_API_KEY"] = body.openai_api_key

    # Write to .env file
    _write_env_file()

    return {"status": "ok"}


def _write_env_file() -> None:
    """Write current API keys to the .env file."""
    lines = []
    anthropic = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if anthropic:
        lines.append(f"ANTHROPIC_API_KEY={anthropic}")
    if openai_key:
        lines.append(f"OPENAI_API_KEY={openai_key}")
    _env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

Update `src/story_video/web/app.py` — add `env_path` parameter to `create_app()` and include the settings router:

```python
"""FastAPI application factory."""

from pathlib import Path

from fastapi import APIRouter, FastAPI

from story_video.web import routes_settings

__all__ = ["create_app"]

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


def create_app(*, env_path: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        env_path: Path to .env file for API key persistence.
            Defaults to .env in current directory.

    Returns:
        Configured FastAPI instance with all routes mounted.
    """
    if env_path is not None:
        routes_settings.configure(env_path)

    app = FastAPI(title="Story Video", version="0.1.0")
    app.include_router(router)
    app.include_router(routes_settings.router)
    return app
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_settings.py -v`
Expected: All passed

Run: `pytest tests/test_web_app.py -v`
Expected: Still passing (no regressions)

**Step 5: Commit**

```bash
git add src/story_video/web/routes_settings.py src/story_video/web/app.py tests/test_web_settings.py
git commit -m "feat(web): add API key setup endpoints (GET/POST /settings/api-keys)"
```

---

## Task 4: Project creation endpoint

**Files:**
- Create: `src/story_video/web/routes_projects.py`
- Create: `tests/test_web_projects.py`
- Modify: `src/story_video/web/app.py`

**Step 1: Write the failing tests**

```python
"""Tests for story_video.web.routes_projects — project CRUD endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

from story_video.web.app import create_app


@pytest.fixture()
def output_dir(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    return d


@pytest.fixture()
def client(output_dir):
    app = create_app(output_dir=output_dir)
    return TestClient(app)


class TestCreateProject:
    """POST /api/v1/projects creates a new project."""

    def test_create_adapt_project_with_source_text(self, client, output_dir):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "Once upon a time there was a story."},
        )
        assert response.status_code == 201
        data = response.json()
        assert "project_id" in data
        assert data["mode"] == "adapt"
        # Project directory exists on disk
        project_dir = output_dir / data["project_id"]
        assert project_dir.exists()
        assert (project_dir / "project.json").exists()

    def test_create_original_project_with_source_text(self, client):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "original", "source_text": "A story about a lighthouse keeper."},
        )
        assert response.status_code == 201
        assert response.json()["mode"] == "original"

    def test_create_inspired_by_project(self, client):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "inspired_by", "source_text": "An inspiring tale."},
        )
        assert response.status_code == 201
        assert response.json()["mode"] == "inspired_by"

    def test_rejects_invalid_mode(self, client):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "invalid", "source_text": "text"},
        )
        assert response.status_code == 422

    def test_requires_source_text(self, client):
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt"},
        )
        assert response.status_code == 422

    def test_source_text_written_to_disk(self, client, output_dir):
        source = "The lighthouse keeper climbed the stairs."
        response = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": source},
        )
        project_id = response.json()["project_id"]
        source_path = output_dir / project_id / "source_story.txt"
        assert source_path.exists()
        assert source_path.read_text(encoding="utf-8") == source


class TestGetProject:
    """GET /api/v1/projects/{id} returns project status."""

    def test_get_existing_project(self, client):
        # Create first
        create_resp = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "A story."},
        )
        project_id = create_resp.json()["project_id"]
        # Fetch
        response = client.get(f"/api/v1/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == project_id
        assert data["mode"] == "adapt"
        assert data["status"] == "pending"
        assert data["current_phase"] is None
        assert "scene_count" in data

    def test_get_nonexistent_project_returns_404(self, client):
        response = client.get("/api/v1/projects/nonexistent")
        assert response.status_code == 404


class TestDeleteProject:
    """DELETE /api/v1/projects/{id} removes the project."""

    def test_delete_existing_project(self, client, output_dir):
        create_resp = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "A story."},
        )
        project_id = create_resp.json()["project_id"]
        project_dir = output_dir / project_id

        response = client.delete(f"/api/v1/projects/{project_id}")
        assert response.status_code == 200
        assert not project_dir.exists()

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete("/api/v1/projects/nonexistent")
        assert response.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_projects.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

`src/story_video/web/routes_projects.py`:
```python
"""Project CRUD routes.

Handles project creation, status queries, and deletion.
All state is managed through ProjectState (project.json on disk).
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from story_video.config import load_config
from story_video.models import InputMode
from story_video.state import ProjectState

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

# Set by create_app() — root directory for project storage.
_output_dir: Path = Path("./output")


def configure(output_dir: Path) -> None:
    """Set the output directory. Called by create_app()."""
    global _output_dir  # noqa: PLW0603
    _output_dir = output_dir


class CreateProjectRequest(BaseModel):
    """Request body for project creation."""

    mode: str
    source_text: str

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        try:
            InputMode(v)
        except ValueError:
            valid = ", ".join(m.value for m in InputMode)
            msg = f"Invalid mode '{v}'. Must be one of: {valid}"
            raise ValueError(msg) from None
        return v

    @field_validator("source_text")
    @classmethod
    def validate_source_text(cls, v: str) -> str:
        if not v.strip():
            msg = "source_text must not be empty"
            raise ValueError(msg)
        return v


def _generate_project_id(mode: str) -> str:
    """Generate a unique project ID like 'adapt-2026-02-25'."""
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    base_id = f"{mode}-{date_str}"
    if not (_output_dir / base_id).exists():
        return base_id
    # Append a numeric suffix to avoid collisions
    for n in range(2, 100):
        candidate = f"{base_id}-{n}"
        if not (_output_dir / candidate).exists():
            return candidate
    msg = f"Too many projects for {date_str}"
    raise RuntimeError(msg)


@router.post("", status_code=201)
async def create_project(body: CreateProjectRequest) -> dict:
    """Create a new story video project.

    Creates the project directory, writes source material to disk,
    and initializes ProjectState.
    """
    mode = InputMode(body.mode)
    config = load_config(None)
    # Web UI always runs semi-auto (pause at checkpoints).
    config = config.model_copy(
        update={"pipeline": config.pipeline.model_copy(update={"autonomous": False})}
    )

    project_id = _generate_project_id(body.mode)
    _output_dir.mkdir(parents=True, exist_ok=True)
    state = ProjectState.create(project_id, mode, config, _output_dir)

    # Write source material
    source_path = state.project_dir / "source_story.txt"
    source_path.write_text(body.source_text, encoding="utf-8")

    return {
        "project_id": project_id,
        "mode": body.mode,
        "project_dir": str(state.project_dir),
    }


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict:
    """Get project status and metadata."""
    state = _load_project(project_id)
    meta = state.metadata
    return {
        "project_id": meta.project_id,
        "mode": meta.mode.value,
        "status": meta.status.value,
        "current_phase": meta.current_phase.value if meta.current_phase else None,
        "scene_count": len(meta.scenes),
        "created_at": meta.created_at.isoformat(),
    }


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> dict:
    """Delete a project and all its files."""
    project_dir = _output_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    shutil.rmtree(project_dir)
    return {"status": "deleted", "project_id": project_id}


def _load_project(project_id: str) -> ProjectState:
    """Load a ProjectState by ID, raising 404 if not found."""
    project_dir = _output_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    try:
        return ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
```

Update `src/story_video/web/app.py` to add `output_dir` parameter and include the projects router:

```python
"""FastAPI application factory."""

from pathlib import Path

from fastapi import APIRouter, FastAPI

from story_video.web import routes_projects, routes_settings

__all__ = ["create_app"]

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


def create_app(
    *,
    env_path: Path | None = None,
    output_dir: Path | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        env_path: Path to .env file for API key persistence.
        output_dir: Root directory for project storage.

    Returns:
        Configured FastAPI instance with all routes mounted.
    """
    if env_path is not None:
        routes_settings.configure(env_path)
    if output_dir is not None:
        routes_projects.configure(output_dir)

    app = FastAPI(title="Story Video", version="0.1.0")
    app.include_router(router)
    app.include_router(routes_settings.router)
    app.include_router(routes_projects.router)
    return app
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_projects.py -v`
Expected: All passed

Run: `pytest tests/test_web_app.py tests/test_web_settings.py -v`
Expected: Still passing

**Step 5: Commit**

```bash
git add src/story_video/web/routes_projects.py src/story_video/web/app.py tests/test_web_projects.py
git commit -m "feat(web): add project CRUD endpoints (create, get, delete)"
```

---

## Task 5: Pipeline start and approve endpoints

**Files:**
- Create: `src/story_video/web/routes_pipeline.py`
- Create: `src/story_video/web/pipeline_runner.py`
- Create: `tests/test_web_pipeline.py`
- Modify: `src/story_video/web/app.py`

This is the core integration — wrapping `run_pipeline()` in a background thread.

**Step 1: Write the failing tests**

```python
"""Tests for story_video.web.routes_pipeline — pipeline start/approve endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from story_video.models import InputMode, PhaseStatus, PipelinePhase
from story_video.state import ProjectState
from story_video.web.app import create_app


@pytest.fixture()
def output_dir(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    return d


@pytest.fixture()
def client(output_dir):
    app = create_app(output_dir=output_dir)
    return TestClient(app)


@pytest.fixture()
def project_id(client):
    """Create a project and return its ID."""
    resp = client.post(
        "/api/v1/projects",
        json={"mode": "adapt", "source_text": "A story about a lighthouse."},
    )
    return resp.json()["project_id"]


class TestStartPipeline:
    """POST /api/v1/projects/{id}/start kicks off the pipeline."""

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_start_returns_202(self, mock_run, client, project_id):
        mock_run.return_value = None
        response = client.post(f"/api/v1/projects/{project_id}/start")
        assert response.status_code == 202
        mock_run.assert_called_once()

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_start_nonexistent_project_returns_404(self, mock_run, client):
        response = client.post("/api/v1/projects/nonexistent/start")
        assert response.status_code == 404
        mock_run.assert_not_called()

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_start_while_running_returns_409(self, mock_run, client, project_id, output_dir):
        # Simulate a running pipeline by setting status to in_progress
        state = ProjectState.load(output_dir / project_id)
        state.start_phase(PipelinePhase.ANALYSIS)
        state.save()

        response = client.post(f"/api/v1/projects/{project_id}/start")
        assert response.status_code == 409
        mock_run.assert_not_called()


class TestApprovePipeline:
    """POST /api/v1/projects/{id}/approve resumes after checkpoint."""

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_approve_awaiting_review_returns_202(self, mock_run, client, project_id, output_dir):
        # Simulate a checkpoint pause
        state = ProjectState.load(output_dir / project_id)
        state.start_phase(PipelinePhase.ANALYSIS)
        state.await_review()
        state.save()

        response = client.post(f"/api/v1/projects/{project_id}/approve")
        assert response.status_code == 202
        mock_run.assert_called_once()

    @patch("story_video.web.pipeline_runner.run_pipeline_in_thread")
    def test_approve_when_not_awaiting_returns_409(self, mock_run, client, project_id):
        response = client.post(f"/api/v1/projects/{project_id}/approve")
        assert response.status_code == 409
        mock_run.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_pipeline.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

`src/story_video/web/pipeline_runner.py`:
```python
"""Background pipeline execution.

Wraps run_pipeline() in a thread so the API can return immediately.
Manages a single active pipeline run (one at a time by design).
"""

import logging
import threading
from collections.abc import Callable

from story_video.pipeline.caption_generator import OpenAIWhisperProvider
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.image_generator import OpenAIImageProvider
from story_video.pipeline.orchestrator import run_pipeline
from story_video.pipeline.tts_generator import (
    ElevenLabsTTSProvider,
    OpenAITTSProvider,
)
from story_video.state import ProjectState

__all__ = ["is_running", "run_pipeline_in_thread"]

logger = logging.getLogger(__name__)

_active_thread: threading.Thread | None = None
_lock = threading.Lock()


def is_running() -> bool:
    """Check if a pipeline is currently running."""
    with _lock:
        return _active_thread is not None and _active_thread.is_alive()


def run_pipeline_in_thread(state: ProjectState) -> None:
    """Start the pipeline in a background thread.

    Args:
        state: Project state to run the pipeline on.

    Raises:
        RuntimeError: If a pipeline is already running.
    """
    global _active_thread  # noqa: PLW0603
    with _lock:
        if _active_thread is not None and _active_thread.is_alive():
            msg = "A pipeline is already running"
            raise RuntimeError(msg)

        thread = threading.Thread(
            target=_run_pipeline_safe,
            args=(state,),
            daemon=True,
        )
        _active_thread = thread
        thread.start()


def _make_tts_provider(provider_name: str) -> OpenAITTSProvider | ElevenLabsTTSProvider:
    """Instantiate a TTS provider by name."""
    if provider_name == "elevenlabs":
        return ElevenLabsTTSProvider()
    return OpenAITTSProvider()


def _run_pipeline_safe(state: ProjectState) -> None:
    """Run the pipeline, catching and logging exceptions."""
    try:
        tts_provider = _make_tts_provider(state.metadata.config.tts.provider)
        run_pipeline(
            state,
            claude_client=ClaudeClient(),
            tts_provider=tts_provider,
            image_provider=OpenAIImageProvider(),
            caption_provider=OpenAIWhisperProvider(),
        )
    except Exception:
        logger.exception("Pipeline failed for project %s", state.metadata.project_id)
```

`src/story_video/web/routes_pipeline.py`:
```python
"""Pipeline control routes — start and approve.

These endpoints delegate to pipeline_runner for background execution.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from story_video.models import PhaseStatus
from story_video.state import ProjectState
from story_video.web import pipeline_runner

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/projects", tags=["pipeline"])

# Set by create_app().
_output_dir: Path = Path("./output")


def configure(output_dir: Path) -> None:
    """Set the output directory. Called by create_app()."""
    global _output_dir  # noqa: PLW0603
    _output_dir = output_dir


@router.post("/{project_id}/start", status_code=202)
async def start_pipeline(project_id: str) -> dict:
    """Start or resume the pipeline for a project.

    Returns 202 Accepted immediately. The pipeline runs in a background thread.
    """
    state = _load_project(project_id)

    # Reject if pipeline is actively in progress
    if state.metadata.status == PhaseStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    pipeline_runner.run_pipeline_in_thread(state)
    return {"status": "started", "project_id": project_id}


@router.post("/{project_id}/approve", status_code=202)
async def approve_checkpoint(project_id: str) -> dict:
    """Approve the current checkpoint and resume the pipeline.

    Only valid when the project status is AWAITING_REVIEW.
    """
    state = _load_project(project_id)

    if state.metadata.status != PhaseStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"Project is not awaiting review (status: {state.metadata.status.value})",
        )

    pipeline_runner.run_pipeline_in_thread(state)
    return {"status": "approved", "project_id": project_id}


def _load_project(project_id: str) -> ProjectState:
    """Load a ProjectState by ID, raising 404 if not found."""
    project_dir = _output_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    try:
        return ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
```

Update `src/story_video/web/app.py` to include the pipeline router:

```python
"""FastAPI application factory."""

from pathlib import Path

from fastapi import APIRouter, FastAPI

from story_video.web import routes_pipeline, routes_projects, routes_settings

__all__ = ["create_app"]

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


def create_app(
    *,
    env_path: Path | None = None,
    output_dir: Path | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    if env_path is not None:
        routes_settings.configure(env_path)
    if output_dir is not None:
        routes_projects.configure(output_dir)
        routes_pipeline.configure(output_dir)

    app = FastAPI(title="Story Video", version="0.1.0")
    app.include_router(router)
    app.include_router(routes_settings.router)
    app.include_router(routes_projects.router)
    app.include_router(routes_pipeline.router)
    return app
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_pipeline.py -v`
Expected: All passed

Run: `pytest tests/test_web_app.py tests/test_web_settings.py tests/test_web_projects.py -v`
Expected: Still passing

**Step 5: Commit**

```bash
git add src/story_video/web/pipeline_runner.py src/story_video/web/routes_pipeline.py src/story_video/web/app.py tests/test_web_pipeline.py
git commit -m "feat(web): add pipeline start/approve endpoints with background thread runner"
```

---

## Task 6: SSE progress bridge

**Files:**
- Create: `src/story_video/web/progress.py`
- Create: `tests/test_web_progress.py`
- Modify: `src/story_video/web/pipeline_runner.py`
- Modify: `src/story_video/web/routes_pipeline.py`

This is the real-time progress streaming infrastructure. The pipeline pushes events to a queue; the SSE endpoint reads from it.

**Step 1: Write the failing tests**

```python
"""Tests for story_video.web.progress — SSE progress bridge."""

import asyncio

import pytest

from story_video.web.progress import ProgressBridge, ProgressEvent


class TestProgressBridge:
    """ProgressBridge queues events and yields them for SSE."""

    def test_push_and_receive_event(self):
        bridge = ProgressBridge()
        bridge.push(ProgressEvent(event="phase_started", data={"phase": "analysis"}))
        # Non-blocking get
        event = bridge.try_get(timeout=0.1)
        assert event is not None
        assert event.event == "phase_started"
        assert event.data["phase"] == "analysis"

    def test_try_get_returns_none_on_empty(self):
        bridge = ProgressBridge()
        event = bridge.try_get(timeout=0.01)
        assert event is None

    def test_multiple_events_in_order(self):
        bridge = ProgressBridge()
        bridge.push(ProgressEvent(event="phase_started", data={"phase": "analysis"}))
        bridge.push(ProgressEvent(event="scene_progress", data={"scene": 1}))
        bridge.push(ProgressEvent(event="completed", data={"video": "final.mp4"}))

        events = []
        for _ in range(3):
            e = bridge.try_get(timeout=0.1)
            assert e is not None
            events.append(e.event)

        assert events == ["phase_started", "scene_progress", "completed"]

    def test_push_completed_marks_done(self):
        bridge = ProgressBridge()
        assert not bridge.is_done
        bridge.push(ProgressEvent(event="completed", data={}))
        assert bridge.is_done

    def test_push_error_marks_done(self):
        bridge = ProgressBridge()
        bridge.push(ProgressEvent(event="error", data={"message": "fail"}))
        assert bridge.is_done

    def test_format_sse_event(self):
        event = ProgressEvent(event="phase_started", data={"phase": "analysis"})
        formatted = event.format_sse()
        assert "event: phase_started" in formatted
        assert '"phase": "analysis"' in formatted
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_progress.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

`src/story_video/web/progress.py`:
```python
"""SSE progress bridge.

Connects the synchronous pipeline thread to the async SSE endpoint
via a thread-safe queue. The pipeline pushes ProgressEvents; the
SSE endpoint reads and streams them to the client.
"""

import json
import queue
from dataclasses import dataclass, field

__all__ = ["ProgressBridge", "ProgressEvent"]

_TERMINAL_EVENTS = frozenset({"completed", "error"})


@dataclass
class ProgressEvent:
    """A single progress event to stream via SSE.

    Attributes:
        event: SSE event type (phase_started, scene_progress, checkpoint, completed, error).
        data: Event payload as a dictionary.
    """

    event: str
    data: dict = field(default_factory=dict)

    def format_sse(self) -> str:
        """Format as an SSE message string."""
        data_str = json.dumps(self.data)
        return f"event: {self.event}\ndata: {data_str}\n\n"


class ProgressBridge:
    """Thread-safe bridge between pipeline thread and SSE endpoint.

    The pipeline thread calls ``push()`` to enqueue events.
    The SSE endpoint calls ``try_get()`` to dequeue them.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[ProgressEvent] = queue.Queue()
        self._done = False

    @property
    def is_done(self) -> bool:
        """Whether a terminal event (completed/error) has been pushed."""
        return self._done

    def push(self, event: ProgressEvent) -> None:
        """Push an event onto the queue.

        If the event is terminal (completed or error), marks the bridge as done.
        """
        if event.event in _TERMINAL_EVENTS:
            self._done = True
        self._queue.put(event)

    def try_get(self, timeout: float = 0.5) -> ProgressEvent | None:
        """Try to get an event from the queue.

        Args:
            timeout: Seconds to wait before returning None.

        Returns:
            The next event, or None if the queue is empty after timeout.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_progress.py -v`
Expected: All passed

**Step 5: Commit**

```bash
git add src/story_video/web/progress.py tests/test_web_progress.py
git commit -m "feat(web): add SSE progress bridge (ProgressBridge + ProgressEvent)"
```

---

## Task 7: Wire progress bridge into pipeline runner and SSE endpoint

**Files:**
- Modify: `src/story_video/web/pipeline_runner.py`
- Modify: `src/story_video/web/routes_pipeline.py`
- Create: `tests/test_web_sse.py`

**Step 1: Write the failing tests**

```python
"""Tests for SSE progress endpoint — GET /api/v1/projects/{id}/progress."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from story_video.models import PipelinePhase
from story_video.state import ProjectState
from story_video.web.app import create_app
from story_video.web.progress import ProgressBridge, ProgressEvent


@pytest.fixture()
def output_dir(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    return d


@pytest.fixture()
def client(output_dir):
    app = create_app(output_dir=output_dir)
    return TestClient(app)


@pytest.fixture()
def project_id(client):
    resp = client.post(
        "/api/v1/projects",
        json={"mode": "adapt", "source_text": "A story."},
    )
    return resp.json()["project_id"]


class TestSSEProgressEndpoint:
    """GET /api/v1/projects/{id}/progress streams SSE events."""

    def test_streams_events_from_bridge(self, client, project_id):
        # Pre-load a bridge with events
        bridge = ProgressBridge()
        bridge.push(ProgressEvent(event="phase_started", data={"phase": "analysis"}))
        bridge.push(ProgressEvent(event="completed", data={}))

        with patch(
            "story_video.web.routes_pipeline.get_bridge",
            return_value=bridge,
        ):
            with client.stream("GET", f"/api/v1/projects/{project_id}/progress") as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                lines = []
                for line in response.iter_lines():
                    lines.append(line)
                    # Stop after we get the completed event
                    if "completed" in line:
                        break

        # We should have received both events
        text = "\n".join(lines)
        assert "phase_started" in text
        assert "completed" in text

    def test_404_for_nonexistent_project(self, client):
        response = client.get("/api/v1/projects/nonexistent/progress")
        assert response.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_sse.py -v`
Expected: FAIL

**Step 3: Update implementation**

Update `src/story_video/web/pipeline_runner.py` to create and track a ProgressBridge per run:

```python
"""Background pipeline execution with progress tracking.

Wraps run_pipeline() in a thread and pushes progress events to a
ProgressBridge that the SSE endpoint reads from.
"""

import logging
import threading

from story_video.pipeline.caption_generator import OpenAIWhisperProvider
from story_video.pipeline.claude_client import ClaudeClient
from story_video.pipeline.image_generator import OpenAIImageProvider
from story_video.pipeline.orchestrator import run_pipeline
from story_video.pipeline.tts_generator import (
    ElevenLabsTTSProvider,
    OpenAITTSProvider,
)
from story_video.state import ProjectState
from story_video.web.progress import ProgressBridge, ProgressEvent

__all__ = ["get_bridge", "is_running", "run_pipeline_in_thread"]

logger = logging.getLogger(__name__)

_active_thread: threading.Thread | None = None
_active_bridge: ProgressBridge | None = None
_lock = threading.Lock()


def is_running() -> bool:
    """Check if a pipeline is currently running."""
    with _lock:
        return _active_thread is not None and _active_thread.is_alive()


def get_bridge() -> ProgressBridge | None:
    """Get the current progress bridge, if any."""
    with _lock:
        return _active_bridge


def run_pipeline_in_thread(state: ProjectState) -> ProgressBridge:
    """Start the pipeline in a background thread.

    Args:
        state: Project state to run the pipeline on.

    Returns:
        ProgressBridge that will receive pipeline events.

    Raises:
        RuntimeError: If a pipeline is already running.
    """
    global _active_thread, _active_bridge  # noqa: PLW0603
    with _lock:
        if _active_thread is not None and _active_thread.is_alive():
            msg = "A pipeline is already running"
            raise RuntimeError(msg)

        bridge = ProgressBridge()
        _active_bridge = bridge

        thread = threading.Thread(
            target=_run_pipeline_safe,
            args=(state, bridge),
            daemon=True,
        )
        _active_thread = thread
        thread.start()

    return bridge


def _make_tts_provider(provider_name: str) -> OpenAITTSProvider | ElevenLabsTTSProvider:
    """Instantiate a TTS provider by name."""
    if provider_name == "elevenlabs":
        return ElevenLabsTTSProvider()
    return OpenAITTSProvider()


def _run_pipeline_safe(state: ProjectState, bridge: ProgressBridge) -> None:
    """Run the pipeline, pushing progress events to the bridge."""
    try:
        tts_provider = _make_tts_provider(state.metadata.config.tts.provider)
        run_pipeline(
            state,
            claude_client=ClaudeClient(),
            tts_provider=tts_provider,
            image_provider=OpenAIImageProvider(),
            caption_provider=OpenAIWhisperProvider(),
        )
        # Pipeline completed or hit a checkpoint.
        # Check if it paused at a checkpoint (AWAITING_REVIEW) or finished.
        state_reloaded = ProjectState.load(state.project_dir)
        if state_reloaded.metadata.status.value == "awaiting_review":
            bridge.push(ProgressEvent(
                event="checkpoint",
                data={
                    "phase": state_reloaded.metadata.current_phase.value
                    if state_reloaded.metadata.current_phase
                    else None,
                },
            ))
        else:
            final_path = state.project_dir / "final.mp4"
            bridge.push(ProgressEvent(
                event="completed",
                data={"video_path": str(final_path) if final_path.exists() else None},
            ))
    except Exception as exc:
        logger.exception("Pipeline failed for project %s", state.metadata.project_id)
        bridge.push(ProgressEvent(
            event="error",
            data={"message": str(exc)},
        ))
```

Update `src/story_video/web/routes_pipeline.py` to add SSE endpoint:

```python
"""Pipeline control routes — start, approve, and progress streaming."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from story_video.models import PhaseStatus
from story_video.state import ProjectState
from story_video.web import pipeline_runner
from story_video.web.progress import ProgressBridge

__all__ = ["get_bridge", "router"]

router = APIRouter(prefix="/api/v1/projects", tags=["pipeline"])

_output_dir: Path = Path("./output")


def configure(output_dir: Path) -> None:
    """Set the output directory. Called by create_app()."""
    global _output_dir  # noqa: PLW0603
    _output_dir = output_dir


def get_bridge() -> ProgressBridge | None:
    """Get the active progress bridge. Exposed for test mocking."""
    return pipeline_runner.get_bridge()


@router.post("/{project_id}/start", status_code=202)
async def start_pipeline(project_id: str) -> dict:
    """Start or resume the pipeline for a project."""
    state = _load_project(project_id)

    if state.metadata.status == PhaseStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    pipeline_runner.run_pipeline_in_thread(state)
    return {"status": "started", "project_id": project_id}


@router.post("/{project_id}/approve", status_code=202)
async def approve_checkpoint(project_id: str) -> dict:
    """Approve the current checkpoint and resume the pipeline."""
    state = _load_project(project_id)

    if state.metadata.status != PhaseStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"Project is not awaiting review (status: {state.metadata.status.value})",
        )

    pipeline_runner.run_pipeline_in_thread(state)
    return {"status": "approved", "project_id": project_id}


@router.get("/{project_id}/progress")
async def stream_progress(project_id: str) -> EventSourceResponse:
    """Stream pipeline progress events via SSE."""
    _verify_project_exists(project_id)

    async def event_generator():
        bridge = get_bridge()
        while True:
            if bridge is None:
                bridge = get_bridge()
                if bridge is None:
                    await asyncio.sleep(0.5)
                    continue

            event = bridge.try_get(timeout=0.1)
            if event is not None:
                yield {"event": event.event, "data": event.format_sse().split("data: ")[1].split("\n")[0]}
                if bridge.is_done:
                    return
            else:
                await asyncio.sleep(0.1)

    return EventSourceResponse(event_generator())


def _verify_project_exists(project_id: str) -> None:
    """Raise 404 if project directory doesn't exist."""
    project_dir = _output_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")


def _load_project(project_id: str) -> ProjectState:
    """Load a ProjectState by ID, raising 404 if not found."""
    project_dir = _output_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    try:
        return ProjectState.load(project_dir)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_sse.py -v`
Expected: All passed

Run: `pytest tests/test_web_pipeline.py tests/test_web_app.py -v`
Expected: Still passing

**Step 5: Commit**

```bash
git add src/story_video/web/pipeline_runner.py src/story_video/web/routes_pipeline.py tests/test_web_sse.py
git commit -m "feat(web): wire SSE progress streaming to pipeline runner"
```

---

## Task 8: Artifact listing and serving endpoints

**Files:**
- Create: `src/story_video/web/routes_artifacts.py`
- Create: `tests/test_web_artifacts.py`
- Modify: `src/story_video/web/app.py`

**Step 1: Write the failing tests**

```python
"""Tests for story_video.web.routes_artifacts — artifact listing and serving."""

import json

import pytest
from fastapi.testclient import TestClient

from story_video.models import InputMode, PipelinePhase
from story_video.state import ProjectState
from story_video.web.app import create_app


@pytest.fixture()
def output_dir(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    return d


@pytest.fixture()
def client(output_dir):
    app = create_app(output_dir=output_dir)
    return TestClient(app)


@pytest.fixture()
def project_with_artifacts(output_dir):
    """Create a project with some artifact files on disk."""
    from story_video.config import load_config

    config = load_config(None)
    state = ProjectState.create("test-project", InputMode.ADAPT, config, output_dir)

    # Write some artifact files mimicking what the pipeline produces
    scenes_dir = state.project_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    (scenes_dir / "analysis.json").write_text(
        json.dumps({"craft_notes": "dramatic tone"}), encoding="utf-8"
    )
    (scenes_dir / "outline.json").write_text(
        json.dumps({"scenes": [{"title": "Opening"}]}), encoding="utf-8"
    )

    images_dir = state.project_dir / "images"
    images_dir.mkdir(exist_ok=True)
    # Write a tiny PNG header (just enough to serve)
    (images_dir / "scene_001_000.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    audio_dir = state.project_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    (audio_dir / "scene_001.mp3").write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 100)

    return state


class TestListArtifacts:
    """GET /api/v1/projects/{id}/artifacts/{phase} lists phase artifacts."""

    def test_list_analysis_artifacts(self, client, project_with_artifacts):
        response = client.get("/api/v1/projects/test-project/artifacts/analysis")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        filenames = [f["name"] for f in data["files"]]
        assert "analysis.json" in filenames

    def test_list_image_generation_artifacts(self, client, project_with_artifacts):
        response = client.get("/api/v1/projects/test-project/artifacts/image_generation")
        assert response.status_code == 200
        data = response.json()
        filenames = [f["name"] for f in data["files"]]
        assert "scene_001_000.png" in filenames

    def test_nonexistent_project_returns_404(self, client):
        response = client.get("/api/v1/projects/nonexistent/artifacts/analysis")
        assert response.status_code == 404

    def test_invalid_phase_returns_422(self, client, project_with_artifacts):
        response = client.get("/api/v1/projects/test-project/artifacts/invalid_phase")
        assert response.status_code == 422


class TestGetArtifact:
    """GET /api/v1/projects/{id}/artifacts/{phase}/{filename} serves a file."""

    def test_serve_json_artifact(self, client, project_with_artifacts):
        response = client.get("/api/v1/projects/test-project/artifacts/analysis/analysis.json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert data["craft_notes"] == "dramatic tone"

    def test_serve_image_artifact(self, client, project_with_artifacts):
        response = client.get(
            "/api/v1/projects/test-project/artifacts/image_generation/scene_001_000.png"
        )
        assert response.status_code == 200
        assert "image/png" in response.headers["content-type"]

    def test_serve_audio_artifact(self, client, project_with_artifacts):
        response = client.get(
            "/api/v1/projects/test-project/artifacts/tts_generation/scene_001.mp3"
        )
        assert response.status_code == 200
        assert "audio" in response.headers["content-type"]

    def test_nonexistent_file_returns_404(self, client, project_with_artifacts):
        response = client.get(
            "/api/v1/projects/test-project/artifacts/analysis/nonexistent.json"
        )
        assert response.status_code == 404

    def test_path_traversal_rejected(self, client, project_with_artifacts):
        response = client.get(
            "/api/v1/projects/test-project/artifacts/analysis/../../pyproject.toml"
        )
        assert response.status_code == 400


class TestUpdateArtifact:
    """PUT /api/v1/projects/{id}/artifacts/{phase}/{filename} updates a file."""

    def test_update_json_artifact(self, client, project_with_artifacts):
        new_content = {"craft_notes": "updated tone", "style": "poetic"}
        response = client.put(
            "/api/v1/projects/test-project/artifacts/analysis/analysis.json",
            json={"content": json.dumps(new_content)},
        )
        assert response.status_code == 200
        # Verify file was updated on disk
        fetch = client.get("/api/v1/projects/test-project/artifacts/analysis/analysis.json")
        assert fetch.json()["craft_notes"] == "updated tone"

    def test_update_nonexistent_file_returns_404(self, client, project_with_artifacts):
        response = client.put(
            "/api/v1/projects/test-project/artifacts/analysis/nonexistent.json",
            json={"content": "new content"},
        )
        assert response.status_code == 404

    def test_update_rejects_empty_content(self, client, project_with_artifacts):
        response = client.put(
            "/api/v1/projects/test-project/artifacts/analysis/analysis.json",
            json={"content": "  "},
        )
        assert response.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_artifacts.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

`src/story_video/web/routes_artifacts.py`:
```python
"""Artifact serving and editing routes.

Serves pipeline-generated files (JSON, images, audio, video) from
the project directory. Supports inline editing of text/JSON artifacts.
"""

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from story_video.models import PipelinePhase

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/projects", tags=["artifacts"])

_output_dir: Path = Path("./output")

# Map pipeline phases to the subdirectory where their artifacts live.
_PHASE_DIRS: dict[str, str] = {
    "analysis": "scenes",
    "story_bible": "scenes",
    "outline": "scenes",
    "scene_prose": "scenes",
    "critique_revision": "scenes",
    "scene_splitting": "scenes",
    "narration_flagging": "scenes",
    "image_prompts": "scenes",
    "narration_prep": "scenes",
    "tts_generation": "audio",
    "image_generation": "images",
    "caption_generation": "captions",
    "video_assembly": "segments",
}


def configure(output_dir: Path) -> None:
    """Set the output directory. Called by create_app()."""
    global _output_dir  # noqa: PLW0603
    _output_dir = output_dir


def _validate_phase(phase: str) -> str:
    """Validate that the phase string is a known PipelinePhase value."""
    try:
        PipelinePhase(phase)
    except ValueError:
        valid = ", ".join(p.value for p in PipelinePhase)
        raise HTTPException(
            status_code=422,
            detail=f"Invalid phase '{phase}'. Must be one of: {valid}",
        ) from None
    return phase


def _resolve_artifact_dir(project_id: str, phase: str) -> Path:
    """Resolve the artifact directory for a project/phase combination."""
    project_dir = _output_dir / project_id
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    _validate_phase(phase)
    subdir = _PHASE_DIRS.get(phase, "scenes")
    return project_dir / subdir


def _guard_path_traversal(base_dir: Path, filename: str) -> Path:
    """Resolve filename within base_dir, rejecting path traversal."""
    resolved = (base_dir / filename).resolve()
    if not resolved.is_relative_to(base_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename (path traversal)")
    return resolved


@router.get("/{project_id}/artifacts/{phase}")
async def list_artifacts(project_id: str, phase: str) -> dict:
    """List artifact files for a pipeline phase."""
    artifact_dir = _resolve_artifact_dir(project_id, phase)
    if not artifact_dir.exists():
        return {"files": []}

    files = []
    for path in sorted(artifact_dir.iterdir()):
        if path.is_file():
            mime, _ = mimetypes.guess_type(path.name)
            files.append({
                "name": path.name,
                "size": path.stat().st_size,
                "content_type": mime or "application/octet-stream",
            })

    return {"files": files}


@router.get("/{project_id}/artifacts/{phase}/{filename}")
async def get_artifact(project_id: str, phase: str, filename: str) -> FileResponse:
    """Serve a specific artifact file."""
    artifact_dir = _resolve_artifact_dir(project_id, phase)
    file_path = _guard_path_traversal(artifact_dir, filename)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    mime, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(file_path, media_type=mime or "application/octet-stream")


class UpdateArtifactRequest(BaseModel):
    """Request body for updating an artifact."""

    content: str

    @field_validator("content")
    @classmethod
    def reject_blank(cls, v: str) -> str:
        if not v.strip():
            msg = "Content must not be blank"
            raise ValueError(msg)
        return v


@router.put("/{project_id}/artifacts/{phase}/{filename}")
async def update_artifact(
    project_id: str, phase: str, filename: str, body: UpdateArtifactRequest
) -> dict:
    """Update the contents of a text/JSON artifact."""
    artifact_dir = _resolve_artifact_dir(project_id, phase)
    file_path = _guard_path_traversal(artifact_dir, filename)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    file_path.write_text(body.content, encoding="utf-8")
    return {"status": "updated", "filename": filename}
```

Update `src/story_video/web/app.py` to include the artifacts router:

```python
"""FastAPI application factory."""

from pathlib import Path

from fastapi import APIRouter, FastAPI

from story_video.web import routes_artifacts, routes_pipeline, routes_projects, routes_settings

__all__ = ["create_app"]

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


def create_app(
    *,
    env_path: Path | None = None,
    output_dir: Path | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    if env_path is not None:
        routes_settings.configure(env_path)
    if output_dir is not None:
        routes_projects.configure(output_dir)
        routes_pipeline.configure(output_dir)
        routes_artifacts.configure(output_dir)

    app = FastAPI(title="Story Video", version="0.1.0")
    app.include_router(router)
    app.include_router(routes_settings.router)
    app.include_router(routes_projects.router)
    app.include_router(routes_pipeline.router)
    app.include_router(routes_artifacts.router)
    return app
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_artifacts.py -v`
Expected: All passed

Run: `pytest tests/test_web_app.py tests/test_web_settings.py tests/test_web_projects.py tests/test_web_pipeline.py tests/test_web_sse.py -v`
Expected: Still passing

**Step 5: Commit**

```bash
git add src/story_video/web/routes_artifacts.py src/story_video/web/app.py tests/test_web_artifacts.py
git commit -m "feat(web): add artifact listing, serving, and editing endpoints"
```

---

## Task 9: Serve CLI command (`python -m story_video serve`)

**Files:**
- Modify: `src/story_video/cli.py`
- Create: `tests/test_web_serve_command.py`

**Step 1: Write the failing tests**

```python
"""Tests for the 'serve' CLI command."""

from unittest.mock import patch

from typer.testing import CliRunner

from story_video.cli import app

runner = CliRunner()


class TestServeCommand:
    """story-video serve starts the web server."""

    @patch("story_video.cli.uvicorn_run")
    def test_serve_default_port(self, mock_uvicorn):
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        mock_uvicorn.assert_called_once()
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs["port"] == 8033

    @patch("story_video.cli.uvicorn_run")
    def test_serve_custom_port(self, mock_uvicorn):
        result = runner.invoke(app, ["serve", "--port", "9000"])
        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs["port"] == 9000

    @patch("story_video.cli.uvicorn_run")
    def test_serve_custom_host(self, mock_uvicorn):
        result = runner.invoke(app, ["serve", "--host", "0.0.0.0"])
        assert result.exit_code == 0
        call_kwargs = mock_uvicorn.call_args
        assert call_kwargs.kwargs["host"] == "0.0.0.0"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_serve_command.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add to the bottom of `src/story_video/cli.py` (before any trailing blank lines), after the existing commands:

```python
# Import uvicorn.run with an alias so tests can mock it
try:
    from uvicorn import run as uvicorn_run
except ImportError:
    uvicorn_run = None  # type: ignore[assignment]


@app.command()
def serve(
    port: int = typer.Option(8033, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    output_dir: Path = typer.Option(
        Path("./output"), "--output-dir", "-o", help="Root directory for projects"
    ),
) -> None:
    """Start the web UI server."""
    if uvicorn_run is None:
        typer.echo("Web dependencies not installed. Run: pip install -e '.[web]'", err=True)
        raise typer.Exit(code=1)

    from story_video.web.app import create_app

    app_instance = create_app(output_dir=output_dir)
    uvicorn_run(app_instance, host=host, port=port)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_serve_command.py -v`
Expected: All passed

Run: `pytest -v`
Expected: All tests passing

**Step 5: Commit**

```bash
git add src/story_video/cli.py tests/test_web_serve_command.py
git commit -m "feat(web): add 'serve' CLI command (python -m story_video serve)"
```

---

## Task 10: Final integration test — full create-to-progress flow

**Files:**
- Create: `tests/test_web_integration.py`

This test verifies the full wiring: create project → start pipeline (mocked) → receive SSE events.

**Step 1: Write the test**

```python
"""Integration test — full create-to-checkpoint flow via web API."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from story_video.web.app import create_app
from story_video.web.progress import ProgressBridge, ProgressEvent


@pytest.fixture()
def output_dir(tmp_path):
    d = tmp_path / "projects"
    d.mkdir()
    return d


@pytest.fixture()
def client(output_dir):
    app = create_app(output_dir=output_dir)
    return TestClient(app)


class TestCreateToProgressFlow:
    """Full flow: create project → start pipeline → receive progress events."""

    def test_create_start_and_receive_checkpoint(self, client):
        # 1. Create project
        create_resp = client.post(
            "/api/v1/projects",
            json={"mode": "adapt", "source_text": "A lighthouse keeper story."},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["project_id"]

        # 2. Prepare a bridge that simulates a checkpoint
        bridge = ProgressBridge()
        bridge.push(
            ProgressEvent(event="phase_started", data={"phase": "analysis", "scene_count": 0})
        )
        bridge.push(
            ProgressEvent(event="checkpoint", data={"phase": "analysis", "artifacts": []})
        )

        # 3. Start pipeline (mocked) and stream progress
        with patch(
            "story_video.web.pipeline_runner.run_pipeline_in_thread",
            return_value=bridge,
        ):
            start_resp = client.post(f"/api/v1/projects/{project_id}/start")
            assert start_resp.status_code == 202

        # 4. Stream progress from the bridge
        with patch("story_video.web.routes_pipeline.get_bridge", return_value=bridge):
            with client.stream(
                "GET", f"/api/v1/projects/{project_id}/progress"
            ) as response:
                assert response.status_code == 200
                lines = list(response.iter_lines())

        text = "\n".join(lines)
        assert "phase_started" in text
        assert "checkpoint" in text

    def test_project_status_reflects_state(self, client):
        # Create and verify initial status
        create_resp = client.post(
            "/api/v1/projects",
            json={"mode": "original", "source_text": "A topic for a story."},
        )
        project_id = create_resp.json()["project_id"]

        status_resp = client.get(f"/api/v1/projects/{project_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["status"] == "pending"
        assert data["current_phase"] is None
        assert data["scene_count"] == 0
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_web_integration.py -v`
Expected: All passed

**Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests passing (existing 870 + new web tests)

**Step 4: Commit**

```bash
git add tests/test_web_integration.py
git commit -m "test(web): add integration test for create-to-progress flow"
```

---

## Task 11: Update BUGS_AND_TODOS.md and DEVELOPMENT.md

**Files:**
- Modify: `BUGS_AND_TODOS.md`
- Modify: `DEVELOPMENT.md`

**Step 1: Update BUGS_AND_TODOS.md**

Mark the web UI backend as in progress. Add a new entry in the active tasks section:

```markdown
- [ ] **Web UI backend API** — FastAPI backend with project CRUD, pipeline start/approve, SSE progress streaming, artifact serving, and API key setup. Plan 1 of 3 for web UI. (Plan: `docs/plans/2026-02-25-web-ui-backend-implementation.md`)
```

**Step 2: Update DEVELOPMENT.md**

Add ADR-011:

```markdown
### ADR-011: Web UI via FastAPI + React SPA

The web UI wraps the existing pipeline in a FastAPI backend. No database — all state lives on disk via `ProjectState`. The pipeline runs in a background thread; progress events flow through a `ProgressBridge` (thread-safe queue) to an SSE endpoint. The React frontend (Plan 2) will consume these endpoints.

Key integration point: `pipeline_runner.run_pipeline_in_thread()` is the only bridge between web and pipeline code. The pipeline itself is unaware of the web layer.

See `docs/plans/2026-02-25-web-ui-design.md` for the full design.
```

**Step 3: Commit**

```bash
git add BUGS_AND_TODOS.md DEVELOPMENT.md
git commit -m "docs: add ADR-011 for web UI, update backlog"
```

---

## Retrospective

(To be filled in after implementation.)

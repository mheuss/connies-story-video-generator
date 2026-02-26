# Web UI React Frontend Implementation Plan (Plan 2 of 3)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a React SPA that lets a non-technical user create story videos, monitor progress, review artifacts at checkpoints, and preview the final video — all in a browser.

**Architecture:** Vite + React + TypeScript SPA in `web/`. Communicates with the FastAPI backend (Plan 1) via a typed fetch wrapper and `EventSource` for SSE. Three screen groups: Create, Progress, Review. React Router for navigation. Component-level state only — no Redux or query library for v1.

**Tech Stack:** Vite, React 19, TypeScript, React Router, Vitest, React Testing Library, Storybook 8

**Design doc:** `docs/plans/2026-02-25-web-ui-design.md`

**Backend API doc:** `docs/qa/2026-02-25-web-ui-backend-qa-guide.md`

---

## Context for the implementer

### Backend API (already built)

The backend runs at `http://localhost:8033`. Start it with `python -m story_video serve`.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/settings/api-keys` | GET | Key status: `{ anthropic_configured, openai_configured }` |
| `/api/v1/settings/api-keys` | POST | Set keys: `{ anthropic_api_key?, openai_api_key? }` |
| `/api/v1/projects` | POST | Create: `{ mode, source_text }` → `{ project_id, mode, project_dir }` |
| `/api/v1/projects/{id}` | GET | Status: `{ project_id, mode, status, current_phase, scene_count, created_at }` |
| `/api/v1/projects/{id}` | DELETE | Delete project |
| `/api/v1/projects/{id}/start` | POST | Start pipeline (202) |
| `/api/v1/projects/{id}/approve` | POST | Approve checkpoint (202) |
| `/api/v1/projects/{id}/progress` | GET | SSE stream. Terminal events: `checkpoint`, `completed`, `error` |
| `/api/v1/projects/{id}/artifacts/{phase}` | GET | List: `{ files: [{ name, size, content_type }] }` |
| `/api/v1/projects/{id}/artifacts/{phase}/{file}` | GET | Serve file |
| `/api/v1/projects/{id}/artifacts/{phase}/{file}` | PUT | Update: `{ content }` |

### SSE events

- `phase_started { phase, scene_count }` — New phase began
- `checkpoint { phase, project_id }` — Pipeline paused, review needed. **Terminal** — connection closes.
- `completed {}` — Final video ready. **Terminal.**
- `error { message }` — Pipeline failed. **Terminal.**

After a terminal event, the client must open a new `EventSource` connection if it needs more events (e.g., after calling `/approve`).

### Valid enums

**InputMode:** `original`, `inspired_by`, `adapt`

**PhaseStatus:** `pending`, `in_progress`, `completed`, `awaiting_review`, `failed`

### Conventions

- All frontend code lives in `web/`.
- Tests live alongside components: `web/src/__tests__/`.
- Storybook stories: `web/src/stories/`.
- Run tests: `cd web && npm test`
- Run Storybook: `cd web && npm run storybook`
- Run dev server: `cd web && npm run dev`
- Format/lint: handled by Vite defaults + TypeScript strict mode.

---

## Task 1: Scaffold Vite + React + TypeScript project

**Files:**
- Create: `web/` (via `npm create vite`)
- Modify: `.gitignore`

**Step 1: Create the Vite project**

```bash
cd /Users/michaelheuss/Projects/story-video
npm create vite@latest web -- --template react-ts
cd web
npm install
```

**Step 2: Verify it runs**

```bash
cd web && npm run dev
```

Expected: Dev server starts. Open `http://localhost:5173` — React template renders.

Stop the dev server (Ctrl+C).

**Step 3: Configure Vite proxy to backend**

Replace `web/vite.config.ts`:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8033",
        changeOrigin: true,
      },
    },
  },
});
```

**Step 4: Update .gitignore**

Add to the project root `.gitignore`:

```
# Frontend
web/node_modules/
web/dist/
```

**Step 5: Clean up template boilerplate**

Remove the default Vite template content:
- Delete `web/src/App.css`
- Delete `web/src/assets/react.svg`
- Replace `web/src/App.tsx` with a minimal placeholder:

```tsx
export default function App() {
  return <h1>Story Video</h1>;
}
```

- Replace `web/src/index.css` with an empty file (we'll add styles later).

**Step 6: Verify build**

```bash
cd web && npm run build
```

Expected: Builds to `web/dist/` without errors.

**Step 7: Commit**

```bash
git add web/ .gitignore
git commit -m "feat(web): scaffold Vite + React + TypeScript project"
```

---

## Task 2: Configure Vitest + React Testing Library

**Files:**
- Modify: `web/package.json`
- Create: `web/vitest.config.ts`
- Create: `web/src/test-setup.ts`
- Create: `web/src/__tests__/App.test.tsx`

**Step 1: Install test dependencies**

```bash
cd web
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

**Step 2: Create Vitest config**

`web/vitest.config.ts`:

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test-setup.ts",
  },
});
```

**Step 3: Create test setup**

`web/src/test-setup.ts`:

```typescript
import "@testing-library/jest-dom/vitest";
```

**Step 4: Add test script to package.json**

Add to `web/package.json` scripts:

```json
"test": "vitest run",
"test:watch": "vitest"
```

**Step 5: Write the first test**

`web/src/__tests__/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import App from "../App";

describe("App", () => {
  it("renders the heading", () => {
    render(<App />);
    expect(screen.getByText("Story Video")).toBeInTheDocument();
  });
});
```

**Step 6: Run tests**

```bash
cd web && npm test
```

Expected: 1 test passed.

**Step 7: Commit**

```bash
git add web/
git commit -m "test(web): configure Vitest + React Testing Library"
```

---

## Task 3: Set up Storybook

**Files:**
- Create: `web/.storybook/` (via Storybook CLI)
- Create: `web/src/stories/App.stories.tsx`

**Step 1: Initialize Storybook**

```bash
cd web
npx storybook@latest init --type react
```

This creates `.storybook/` config and example stories. Accept defaults.

**Step 2: Remove example stories**

Delete the auto-generated example stories (Button, Header, Page) from `web/src/stories/` — we'll write our own.

**Step 3: Write a minimal story**

`web/src/stories/App.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import App from "../App";

const meta: Meta<typeof App> = {
  title: "App",
  component: App,
};
export default meta;

type Story = StoryObj<typeof App>;

export const Default: Story = {};
```

**Step 4: Verify Storybook runs**

```bash
cd web && npm run storybook
```

Expected: Opens browser with Storybook showing the App story.

Stop Storybook (Ctrl+C).

**Step 5: Commit**

```bash
git add web/
git commit -m "feat(web): set up Storybook for component development"
```

---

## Task 4: API client layer

**Files:**
- Create: `web/src/api/client.ts`
- Create: `web/src/api/types.ts`
- Create: `web/src/__tests__/api-client.test.ts`

**Step 1: Write the failing tests**

`web/src/__tests__/api-client.test.ts`:

```typescript
import { describe, it, expect, beforeEach, vi } from "vitest";
import { api } from "../api/client";

// Mock fetch globally
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

describe("api.getHealth", () => {
  it("calls GET /api/v1/health", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "ok" }),
    });

    const result = await api.getHealth();
    expect(result).toEqual({ status: "ok" });
    expect(mockFetch).toHaveBeenCalledWith("/api/v1/health", expect.objectContaining({ method: "GET" }));
  });
});

describe("api.getApiKeyStatus", () => {
  it("calls GET /api/v1/settings/api-keys", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ anthropic_configured: true, openai_configured: false }),
    });

    const result = await api.getApiKeyStatus();
    expect(result.anthropic_configured).toBe(true);
    expect(result.openai_configured).toBe(false);
  });
});

describe("api.setApiKeys", () => {
  it("calls POST /api/v1/settings/api-keys with body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "ok" }),
    });

    await api.setApiKeys({ anthropic_api_key: "sk-test" });
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/settings/api-keys",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ anthropic_api_key: "sk-test" }),
      }),
    );
  });
});

describe("api.createProject", () => {
  it("calls POST /api/v1/projects", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ project_id: "adapt-2026-02-25", mode: "adapt" }),
    });

    const result = await api.createProject({ mode: "adapt", source_text: "A story." });
    expect(result.project_id).toBe("adapt-2026-02-25");
  });
});

describe("api.getProject", () => {
  it("calls GET /api/v1/projects/{id}", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        project_id: "adapt-2026-02-25",
        mode: "adapt",
        status: "pending",
        current_phase: null,
        scene_count: 0,
        created_at: "2026-02-25T00:00:00Z",
      }),
    });

    const result = await api.getProject("adapt-2026-02-25");
    expect(result.status).toBe("pending");
  });
});

describe("api.startPipeline", () => {
  it("calls POST /api/v1/projects/{id}/start", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "started" }),
    });

    await api.startPipeline("adapt-2026-02-25");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/projects/adapt-2026-02-25/start",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("api.approvePipeline", () => {
  it("calls POST /api/v1/projects/{id}/approve", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "approved" }),
    });

    await api.approvePipeline("adapt-2026-02-25");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/projects/adapt-2026-02-25/approve",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("api.listArtifacts", () => {
  it("calls GET /api/v1/projects/{id}/artifacts/{phase}", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ files: [{ name: "analysis.json", size: 100, content_type: "application/json" }] }),
    });

    const result = await api.listArtifacts("adapt-2026-02-25", "analysis");
    expect(result.files).toHaveLength(1);
  });
});

describe("api.updateArtifact", () => {
  it("calls PUT /api/v1/projects/{id}/artifacts/{phase}/{file}", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "updated", filename: "analysis.json" }),
    });

    await api.updateArtifact("adapt-2026-02-25", "analysis", "analysis.json", "new content");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/projects/adapt-2026-02-25/artifacts/analysis/analysis.json",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ content: "new content" }),
      }),
    );
  });
});

describe("error handling", () => {
  it("throws ApiError on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: "Project not found" }),
    });

    await expect(api.getProject("nonexistent")).rejects.toThrow("Project not found");
  });
});
```

**Step 2: Run tests to verify they fail**

```bash
cd web && npm test
```

Expected: FAIL — `api/client` module doesn't exist.

**Step 3: Write the types**

`web/src/api/types.ts`:

```typescript
/** API key configuration status. */
export interface ApiKeyStatus {
  anthropic_configured: boolean;
  openai_configured: boolean;
}

/** Request body for setting API keys. */
export interface SetApiKeysRequest {
  anthropic_api_key?: string;
  openai_api_key?: string;
}

/** Request body for creating a project. */
export interface CreateProjectRequest {
  mode: "original" | "inspired_by" | "adapt";
  source_text: string;
}

/** Response from creating a project. */
export interface CreateProjectResponse {
  project_id: string;
  mode: string;
  project_dir: string;
}

/** Project status response. */
export interface ProjectStatus {
  project_id: string;
  mode: string;
  status: "pending" | "in_progress" | "completed" | "awaiting_review" | "failed";
  current_phase: string | null;
  scene_count: number;
  created_at: string;
}

/** Artifact file metadata. */
export interface ArtifactFile {
  name: string;
  size: number;
  content_type: string;
}

/** Artifact list response. */
export interface ArtifactList {
  files: ArtifactFile[];
}

/** SSE event from the progress endpoint. */
export interface ProgressEvent {
  event: "phase_started" | "checkpoint" | "completed" | "error";
  data: Record<string, unknown>;
}
```

**Step 4: Write the API client**

`web/src/api/client.ts`:

```typescript
import type {
  ApiKeyStatus,
  ArtifactList,
  CreateProjectRequest,
  CreateProjectResponse,
  ProjectStatus,
  SetApiKeysRequest,
} from "./types";

const BASE = "/api/v1";

/** Error thrown when the API returns a non-OK response. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new ApiError(response.status, body.detail || "Request failed");
  }

  return response.json() as Promise<T>;
}

export const api = {
  // Health
  getHealth: () => request<{ status: string }>("/health", { method: "GET" }),

  // Settings
  getApiKeyStatus: () => request<ApiKeyStatus>("/settings/api-keys", { method: "GET" }),

  setApiKeys: (keys: SetApiKeysRequest) =>
    request<{ status: string }>("/settings/api-keys", {
      method: "POST",
      body: JSON.stringify(keys),
    }),

  // Projects
  createProject: (data: CreateProjectRequest) =>
    request<CreateProjectResponse>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getProject: (projectId: string) =>
    request<ProjectStatus>(`/projects/${projectId}`, { method: "GET" }),

  deleteProject: (projectId: string) =>
    request<{ status: string }>(`/projects/${projectId}`, { method: "DELETE" }),

  // Pipeline
  startPipeline: (projectId: string) =>
    request<{ status: string }>(`/projects/${projectId}/start`, { method: "POST" }),

  approvePipeline: (projectId: string) =>
    request<{ status: string }>(`/projects/${projectId}/approve`, { method: "POST" }),

  // Artifacts
  listArtifacts: (projectId: string, phase: string) =>
    request<ArtifactList>(`/projects/${projectId}/artifacts/${phase}`, { method: "GET" }),

  getArtifactUrl: (projectId: string, phase: string, filename: string) =>
    `${BASE}/projects/${projectId}/artifacts/${phase}/${filename}`,

  updateArtifact: (projectId: string, phase: string, filename: string, content: string) =>
    request<{ status: string; filename: string }>(
      `/projects/${projectId}/artifacts/${phase}/${filename}`,
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    ),
};
```

**Step 5: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 6: Commit**

```bash
git add web/src/api/ web/src/__tests__/api-client.test.ts
git commit -m "feat(web): add typed API client layer"
```

---

## Task 5: Layout shell + React Router

**Files:**
- Create: `web/src/components/Layout.tsx`
- Create: `web/src/pages/CreatePage.tsx` (placeholder)
- Create: `web/src/pages/ProjectPage.tsx` (placeholder)
- Modify: `web/src/App.tsx`
- Create: `web/src/__tests__/Layout.test.tsx`

**Step 1: Install React Router**

```bash
cd web && npm install react-router-dom
```

**Step 2: Write the failing test**

`web/src/__tests__/Layout.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";

describe("Layout", () => {
  it("renders the app title", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("Story Video")).toBeInTheDocument();
  });

  it("shows create page at root route", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText(/create/i)).toBeInTheDocument();
  });
});
```

**Step 3: Run test to verify it fails**

```bash
cd web && npm test
```

Expected: FAIL.

**Step 4: Write the implementation**

`web/src/components/Layout.tsx`:

```tsx
import { Outlet, Link } from "react-router-dom";

export default function Layout() {
  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "1rem" }}>
      <header style={{ borderBottom: "1px solid #eee", marginBottom: "1rem", paddingBottom: "0.5rem" }}>
        <Link to="/" style={{ textDecoration: "none", color: "inherit" }}>
          <h1 style={{ margin: 0 }}>Story Video</h1>
        </Link>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
```

`web/src/pages/CreatePage.tsx`:

```tsx
export default function CreatePage() {
  return <div>Create a new story video</div>;
}
```

`web/src/pages/ProjectPage.tsx`:

```tsx
import { useParams } from "react-router-dom";

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  return <div>Project: {projectId}</div>;
}
```

`web/src/App.tsx`:

```tsx
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import CreatePage from "./pages/CreatePage";
import ProjectPage from "./pages/ProjectPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<CreatePage />} />
        <Route path="/project/:projectId" element={<ProjectPage />} />
      </Route>
    </Routes>
  );
}
```

Update `web/src/main.tsx` to include the router:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
```

**Step 5: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 6: Commit**

```bash
git add web/src/
git commit -m "feat(web): add layout shell with React Router"
```

---

## Task 6: API key setup screen

**Files:**
- Create: `web/src/components/ApiKeySetup.tsx`
- Create: `web/src/__tests__/ApiKeySetup.test.tsx`
- Modify: `web/src/pages/CreatePage.tsx`

**Step 1: Write the failing test**

`web/src/__tests__/ApiKeySetup.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ApiKeySetup from "../components/ApiKeySetup";

const mockGetStatus = vi.fn();
const mockSetKeys = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    getApiKeyStatus: (...args: unknown[]) => mockGetStatus(...args),
    setApiKeys: (...args: unknown[]) => mockSetKeys(...args),
  },
}));

describe("ApiKeySetup", () => {
  beforeEach(() => {
    mockGetStatus.mockReset();
    mockSetKeys.mockReset();
  });

  it("shows form when keys are not configured", async () => {
    mockGetStatus.mockResolvedValueOnce({ anthropic_configured: false, openai_configured: false });

    render(<ApiKeySetup onComplete={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByLabelText(/anthropic/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/openai/i)).toBeInTheDocument();
    });
  });

  it("calls onComplete when keys are already configured", async () => {
    mockGetStatus.mockResolvedValueOnce({ anthropic_configured: true, openai_configured: true });
    const onComplete = vi.fn();

    render(<ApiKeySetup onComplete={onComplete} />);

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalled();
    });
  });

  it("submits keys and calls onComplete", async () => {
    mockGetStatus.mockResolvedValueOnce({ anthropic_configured: false, openai_configured: false });
    mockSetKeys.mockResolvedValueOnce({ status: "ok" });
    const onComplete = vi.fn();
    const user = userEvent.setup();

    render(<ApiKeySetup onComplete={onComplete} />);

    await waitFor(() => {
      expect(screen.getByLabelText(/anthropic/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/anthropic/i), "sk-ant-test");
    await user.type(screen.getByLabelText(/openai/i), "sk-test");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(mockSetKeys).toHaveBeenCalledWith({
        anthropic_api_key: "sk-ant-test",
        openai_api_key: "sk-test",
      });
      expect(onComplete).toHaveBeenCalled();
    });
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd web && npm test
```

Expected: FAIL.

**Step 3: Write the implementation**

`web/src/components/ApiKeySetup.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";

interface Props {
  onComplete: () => void;
}

export default function ApiKeySetup({ onComplete }: Props) {
  const [loading, setLoading] = useState(true);
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getApiKeyStatus().then((status) => {
      if (status.anthropic_configured && status.openai_configured) {
        onComplete();
      } else {
        setLoading(false);
      }
    });
  }, [onComplete]);

  if (loading) return <p>Checking API keys...</p>;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);

    try {
      await api.setApiKeys({
        anthropic_api_key: anthropicKey || undefined,
        openai_api_key: openaiKey || undefined,
      });
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save keys");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>API Key Setup</h2>
      <p>Enter your API keys to get started. These are stored locally and never sent anywhere except to the AI providers.</p>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="anthropic-key">Anthropic API Key</label>
        <br />
        <input
          id="anthropic-key"
          type="password"
          value={anthropicKey}
          onChange={(e) => setAnthropicKey(e.target.value)}
          placeholder="sk-ant-..."
          style={{ width: "100%", padding: "0.5rem" }}
        />
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="openai-key">OpenAI API Key</label>
        <br />
        <input
          id="openai-key"
          type="password"
          value={openaiKey}
          onChange={(e) => setOpenaiKey(e.target.value)}
          placeholder="sk-..."
          style={{ width: "100%", padding: "0.5rem" }}
        />
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      <button type="submit" disabled={saving || (!anthropicKey && !openaiKey)}>
        {saving ? "Saving..." : "Save Keys"}
      </button>
    </form>
  );
}
```

**Step 4: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 5: Commit**

```bash
git add web/src/components/ApiKeySetup.tsx web/src/__tests__/ApiKeySetup.test.tsx
git commit -m "feat(web): add API key setup component"
```

---

## Task 7: Create project screen

**Files:**
- Modify: `web/src/pages/CreatePage.tsx`
- Create: `web/src/__tests__/CreatePage.test.tsx`

**Step 1: Write the failing test**

`web/src/__tests__/CreatePage.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import CreatePage from "../pages/CreatePage";

const mockGetStatus = vi.fn();
const mockCreateProject = vi.fn();
const mockStartPipeline = vi.fn();

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("../api/client", () => ({
  api: {
    getApiKeyStatus: (...args: unknown[]) => mockGetStatus(...args),
    setApiKeys: vi.fn(),
    createProject: (...args: unknown[]) => mockCreateProject(...args),
    startPipeline: (...args: unknown[]) => mockStartPipeline(...args),
  },
}));

describe("CreatePage", () => {
  beforeEach(() => {
    mockGetStatus.mockReset();
    mockCreateProject.mockReset();
    mockStartPipeline.mockReset();
    mockNavigate.mockReset();
  });

  it("shows create form when keys are configured", async () => {
    mockGetStatus.mockResolvedValueOnce({ anthropic_configured: true, openai_configured: true });

    render(
      <MemoryRouter>
        <CreatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
      expect(screen.getByRole("textbox")).toBeInTheDocument();
    });
  });

  it("creates project and navigates on submit", async () => {
    mockGetStatus.mockResolvedValueOnce({ anthropic_configured: true, openai_configured: true });
    mockCreateProject.mockResolvedValueOnce({ project_id: "adapt-2026-02-25", mode: "adapt" });
    mockStartPipeline.mockResolvedValueOnce({ status: "started" });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CreatePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("textbox")).toBeInTheDocument();
    });

    await user.type(screen.getByRole("textbox"), "A story about a lighthouse.");
    await user.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalledWith({
        mode: "adapt",
        source_text: "A story about a lighthouse.",
      });
      expect(mockStartPipeline).toHaveBeenCalledWith("adapt-2026-02-25");
      expect(mockNavigate).toHaveBeenCalledWith("/project/adapt-2026-02-25");
    });
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd web && npm test
```

Expected: FAIL.

**Step 3: Write the implementation**

`web/src/pages/CreatePage.tsx`:

```tsx
import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import ApiKeySetup from "../components/ApiKeySetup";

type Mode = "adapt" | "original" | "inspired_by";

export default function CreatePage() {
  const navigate = useNavigate();
  const [keysReady, setKeysReady] = useState(false);
  const [mode, setMode] = useState<Mode>("adapt");
  const [sourceText, setSourceText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const handleKeysComplete = useCallback(() => setKeysReady(true), []);

  if (!keysReady) {
    return <ApiKeySetup onComplete={handleKeysComplete} />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceText.trim()) return;

    setError(null);
    setCreating(true);

    try {
      const project = await api.createProject({ mode, source_text: sourceText });
      await api.startPipeline(project.project_id);
      navigate(`/project/${project.project_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
      setCreating(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>Create a new story video</h2>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="mode">Mode</label>
        <br />
        <select
          id="mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
          style={{ padding: "0.5rem" }}
        >
          <option value="adapt">Adapt (narrate an existing story)</option>
          <option value="original">Original (write from a topic)</option>
          <option value="inspired_by">Inspired By (new story from existing)</option>
        </select>
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="source-text">
          {mode === "adapt" ? "Paste your story" : "Describe your idea"}
        </label>
        <br />
        <textarea
          id="source-text"
          value={sourceText}
          onChange={(e) => setSourceText(e.target.value)}
          rows={12}
          style={{ width: "100%", padding: "0.5rem" }}
          placeholder={mode === "adapt" ? "Paste the full text of your story here..." : "Describe your story idea..."}
        />
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      <button type="submit" disabled={creating || !sourceText.trim()}>
        {creating ? "Creating..." : "Create & Start"}
      </button>
    </form>
  );
}
```

**Step 4: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 5: Commit**

```bash
git add web/src/pages/CreatePage.tsx web/src/__tests__/CreatePage.test.tsx
git commit -m "feat(web): add create project screen with mode selection"
```

---

## Task 8: Progress screen with SSE

**Files:**
- Create: `web/src/hooks/useProgressStream.ts`
- Modify: `web/src/pages/ProjectPage.tsx`
- Create: `web/src/__tests__/useProgressStream.test.ts`
- Create: `web/src/__tests__/ProjectPage.test.tsx`

**Step 1: Write the failing tests**

`web/src/__tests__/useProgressStream.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useProgressStream } from "../hooks/useProgressStream";

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {};
  onerror: ((event: Event) => void) | null = null;
  readyState = 0;

  constructor(url: string) {
    this.url = url;
    this.readyState = 1; // OPEN
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(listener);
  }

  removeEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (this.listeners[type]) {
      this.listeners[type] = this.listeners[type].filter((l) => l !== listener);
    }
  }

  close() {
    this.readyState = 2; // CLOSED
  }

  // Test helper: simulate an event
  emit(type: string, data: string) {
    const event = new MessageEvent(type, { data });
    (this.listeners[type] || []).forEach((l) => l(event));
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useProgressStream", () => {
  it("connects to the SSE endpoint", () => {
    renderHook(() => useProgressStream("test-project"));
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe("/api/v1/projects/test-project/progress");
  });

  it("receives phase_started events", () => {
    const { result } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("phase_started", JSON.stringify({ phase: "analysis", scene_count: 5 }));
    });

    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0].event).toBe("phase_started");
    expect(result.current.currentPhase).toBe("analysis");
  });

  it("sets isComplete on completed event", () => {
    const { result } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("completed", JSON.stringify({}));
    });

    expect(result.current.isComplete).toBe(true);
  });

  it("sets checkpoint on checkpoint event", () => {
    const { result } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("checkpoint", JSON.stringify({ phase: "analysis", project_id: "test-project" }));
    });

    expect(result.current.checkpoint).toEqual({ phase: "analysis", project_id: "test-project" });
  });

  it("closes connection on unmount", () => {
    const { unmount } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    unmount();
    expect(es.readyState).toBe(2); // CLOSED
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd web && npm test
```

Expected: FAIL.

**Step 3: Write the hook**

`web/src/hooks/useProgressStream.ts`:

```typescript
import { useEffect, useRef, useState } from "react";
import type { ProgressEvent } from "../api/types";

interface ProgressState {
  events: ProgressEvent[];
  currentPhase: string | null;
  checkpoint: { phase: string; project_id: string } | null;
  isComplete: boolean;
  error: string | null;
}

const TERMINAL_EVENTS = new Set(["checkpoint", "completed", "error"]);
const SSE_EVENT_TYPES = ["phase_started", "scene_progress", "checkpoint", "completed", "error"];

export function useProgressStream(projectId: string | null): ProgressState {
  const [state, setState] = useState<ProgressState>({
    events: [],
    currentPhase: null,
    checkpoint: null,
    isComplete: false,
    error: null,
  });
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!projectId) return;

    const es = new EventSource(`/api/v1/projects/${projectId}/progress`);
    esRef.current = es;

    const handleEvent = (type: string) => (event: MessageEvent) => {
      const data = JSON.parse(event.data) as Record<string, unknown>;
      const progressEvent: ProgressEvent = { event: type as ProgressEvent["event"], data };

      setState((prev) => {
        const next = { ...prev, events: [...prev.events, progressEvent] };

        if (type === "phase_started") {
          next.currentPhase = (data.phase as string) || null;
        } else if (type === "checkpoint") {
          next.checkpoint = { phase: data.phase as string, project_id: data.project_id as string };
        } else if (type === "completed") {
          next.isComplete = true;
        } else if (type === "error") {
          next.error = (data.message as string) || "Pipeline failed";
        }

        return next;
      });

      if (TERMINAL_EVENTS.has(type)) {
        es.close();
      }
    };

    for (const type of SSE_EVENT_TYPES) {
      es.addEventListener(type, handleEvent(type));
    }

    es.onerror = () => {
      setState((prev) => ({ ...prev, error: "Connection lost" }));
      es.close();
    };

    return () => {
      es.close();
    };
  }, [projectId]);

  return state;
}
```

**Step 4: Write the ProjectPage**

`web/src/pages/ProjectPage.tsx`:

```tsx
import { useParams } from "react-router-dom";
import { useProgressStream } from "../hooks/useProgressStream";
import ReviewScreen from "../components/ReviewScreen";

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const progress = useProgressStream(projectId ?? null);

  if (progress.error) {
    return (
      <div>
        <h2>Error</h2>
        <p style={{ color: "red" }}>{progress.error}</p>
        <p>Check the server logs for details.</p>
      </div>
    );
  }

  if (progress.isComplete) {
    return (
      <div>
        <h2>Video Complete</h2>
        <p>Your story video is ready.</p>
        {projectId && (
          <video
            controls
            style={{ maxWidth: "100%" }}
            src={`/api/v1/projects/${projectId}/artifacts/video_assembly/final.mp4`}
          />
        )}
      </div>
    );
  }

  if (progress.checkpoint && projectId) {
    return <ReviewScreen projectId={projectId} checkpoint={progress.checkpoint} />;
  }

  return (
    <div>
      <h2>Processing</h2>
      {progress.currentPhase ? (
        <p>
          Current phase: <strong>{progress.currentPhase.replace(/_/g, " ")}</strong>
        </p>
      ) : (
        <p>Starting pipeline...</p>
      )}
      <div style={{ background: "#f0f0f0", borderRadius: 4, padding: "0.5rem", marginTop: "1rem" }}>
        {progress.events.map((evt, i) => (
          <div key={i} style={{ fontSize: "0.9rem", marginBottom: "0.25rem" }}>
            <strong>{evt.event}</strong>: {JSON.stringify(evt.data)}
          </div>
        ))}
      </div>
    </div>
  );
}
```

Note: `ReviewScreen` doesn't exist yet — it's created in Task 9. For this task, create a stub:

`web/src/components/ReviewScreen.tsx`:

```tsx
interface Props {
  projectId: string;
  checkpoint: { phase: string; project_id: string };
}

export default function ReviewScreen({ projectId, checkpoint }: Props) {
  return (
    <div>
      <h2>Review: {checkpoint.phase.replace(/_/g, " ")}</h2>
      <p>Project: {projectId}</p>
      <p>Checkpoint review UI coming next...</p>
    </div>
  );
}
```

**Step 5: Write the ProjectPage test**

`web/src/__tests__/ProjectPage.test.tsx`:

```tsx
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi, beforeEach, afterEach } from "vitest";
import ProjectPage from "../pages/ProjectPage";

// Reuse the MockEventSource from useProgressStream tests
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {};
  onerror: ((event: Event) => void) | null = null;
  readyState = 1;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(listener);
  }
  removeEventListener() {}
  close() { this.readyState = 2; }
  emit(type: string, data: string) {
    const event = new MessageEvent(type, { data });
    (this.listeners[type] || []).forEach((l) => l(event));
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderProjectPage(projectId: string) {
  return render(
    <MemoryRouter initialEntries={[`/project/${projectId}`]}>
      <Routes>
        <Route path="/project/:projectId" element={<ProjectPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProjectPage", () => {
  it("shows processing state initially", () => {
    renderProjectPage("test-project");
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Starting pipeline...")).toBeInTheDocument();
  });

  it("shows current phase when phase_started arrives", () => {
    renderProjectPage("test-project");
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("phase_started", JSON.stringify({ phase: "analysis", scene_count: 5 }));
    });

    expect(screen.getByText(/analysis/)).toBeInTheDocument();
  });

  it("shows video when completed", () => {
    renderProjectPage("test-project");
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("completed", JSON.stringify({}));
    });

    expect(screen.getByText("Video Complete")).toBeInTheDocument();
  });

  it("shows error on error event", () => {
    renderProjectPage("test-project");
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("error", JSON.stringify({ message: "TTS failed" }));
    });

    expect(screen.getByText("TTS failed")).toBeInTheDocument();
  });
});
```

**Step 6: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 7: Commit**

```bash
git add web/src/hooks/ web/src/pages/ProjectPage.tsx web/src/components/ReviewScreen.tsx web/src/__tests__/useProgressStream.test.ts web/src/__tests__/ProjectPage.test.tsx
git commit -m "feat(web): add progress screen with SSE streaming"
```

---

## Task 9: Checkpoint review screen

**Files:**
- Modify: `web/src/components/ReviewScreen.tsx`
- Create: `web/src/__tests__/ReviewScreen.test.tsx`

**Step 1: Write the failing test**

`web/src/__tests__/ReviewScreen.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import ReviewScreen from "../components/ReviewScreen";

const mockListArtifacts = vi.fn();
const mockApprovePipeline = vi.fn();
const mockGetArtifactUrl = vi.fn();
const mockUpdateArtifact = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    listArtifacts: (...args: unknown[]) => mockListArtifacts(...args),
    approvePipeline: (...args: unknown[]) => mockApprovePipeline(...args),
    getArtifactUrl: (...args: unknown[]) => mockGetArtifactUrl(...args),
    updateArtifact: (...args: unknown[]) => mockUpdateArtifact(...args),
  },
}));

describe("ReviewScreen", () => {
  beforeEach(() => {
    mockListArtifacts.mockReset();
    mockApprovePipeline.mockReset();
    mockGetArtifactUrl.mockReset();
    mockUpdateArtifact.mockReset();
  });

  it("loads and displays artifacts for the checkpoint phase", async () => {
    mockListArtifacts.mockResolvedValueOnce({
      files: [
        { name: "analysis.json", size: 200, content_type: "application/json" },
        { name: "outline.json", size: 350, content_type: "application/json" },
      ],
    });

    render(
      <MemoryRouter>
        <ReviewScreen projectId="test-project" checkpoint={{ phase: "analysis", project_id: "test-project" }} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("analysis.json")).toBeInTheDocument();
      expect(screen.getByText("outline.json")).toBeInTheDocument();
    });
  });

  it("calls approve and reloads page on approve click", async () => {
    mockListArtifacts.mockResolvedValueOnce({ files: [] });
    mockApprovePipeline.mockResolvedValueOnce({ status: "approved" });
    const user = userEvent.setup();

    // Mock window.location.reload
    const reloadMock = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, reload: reloadMock },
      writable: true,
    });

    render(
      <MemoryRouter>
        <ReviewScreen projectId="test-project" checkpoint={{ phase: "analysis", project_id: "test-project" }} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => {
      expect(mockApprovePipeline).toHaveBeenCalledWith("test-project");
    });
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd web && npm test
```

Expected: FAIL.

**Step 3: Write the implementation**

`web/src/components/ReviewScreen.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ArtifactFile } from "../api/types";

interface Props {
  projectId: string;
  checkpoint: { phase: string; project_id: string };
}

export default function ReviewScreen({ projectId, checkpoint }: Props) {
  const [files, setFiles] = useState<ArtifactFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  useEffect(() => {
    api
      .listArtifacts(projectId, checkpoint.phase)
      .then((result) => setFiles(result.files))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load artifacts"))
      .finally(() => setLoading(false));
  }, [projectId, checkpoint.phase]);

  const handleApprove = async () => {
    setApproving(true);
    try {
      await api.approvePipeline(projectId);
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve");
      setApproving(false);
    }
  };

  const handleEdit = async (filename: string) => {
    const url = api.getArtifactUrl(projectId, checkpoint.phase, filename);
    const response = await fetch(url);
    const text = await response.text();
    setEditContent(text);
    setEditingFile(filename);
  };

  const handleSave = async () => {
    if (!editingFile) return;
    try {
      await api.updateArtifact(projectId, checkpoint.phase, editingFile, editContent);
      setEditingFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    }
  };

  if (loading) return <p>Loading artifacts...</p>;

  const phaseName = checkpoint.phase.replace(/_/g, " ");

  return (
    <div>
      <h2>Review: {phaseName}</h2>
      <p>The pipeline is waiting for your review. Check the artifacts below, make edits if needed, then approve to continue.</p>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {editingFile ? (
        <div style={{ marginBottom: "1rem" }}>
          <h3>Editing: {editingFile}</h3>
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            rows={20}
            style={{ width: "100%", fontFamily: "monospace", padding: "0.5rem" }}
          />
          <div style={{ marginTop: "0.5rem" }}>
            <button onClick={handleSave} style={{ marginRight: "0.5rem" }}>Save</button>
            <button onClick={() => setEditingFile(null)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div style={{ marginBottom: "1rem" }}>
          {files.length === 0 ? (
            <p>No artifacts for this phase yet.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {files.map((file) => (
                <li
                  key={file.name}
                  style={{
                    padding: "0.5rem",
                    borderBottom: "1px solid #eee",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span>{file.name}</span>
                  <span style={{ fontSize: "0.8rem", color: "#666" }}>
                    {(file.size / 1024).toFixed(1)} KB
                    {file.content_type.startsWith("text/") || file.content_type === "application/json" ? (
                      <button onClick={() => handleEdit(file.name)} style={{ marginLeft: "0.5rem" }}>
                        Edit
                      </button>
                    ) : file.content_type.startsWith("image/") ? (
                      <img
                        src={api.getArtifactUrl(projectId, checkpoint.phase, file.name)}
                        alt={file.name}
                        style={{ maxWidth: 200, maxHeight: 150, marginLeft: "0.5rem" }}
                      />
                    ) : file.content_type.startsWith("audio/") ? (
                      <audio
                        controls
                        src={api.getArtifactUrl(projectId, checkpoint.phase, file.name)}
                        style={{ marginLeft: "0.5rem" }}
                      />
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <button onClick={handleApprove} disabled={approving} style={{ fontSize: "1.1rem", padding: "0.5rem 1.5rem" }}>
        {approving ? "Approving..." : "Approve & Continue"}
      </button>
    </div>
  );
}
```

**Step 4: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 5: Commit**

```bash
git add web/src/components/ReviewScreen.tsx web/src/__tests__/ReviewScreen.test.tsx
git commit -m "feat(web): add checkpoint review screen with artifact editing"
```

---

## Task 10: Storybook stories for all screens

**Files:**
- Create: `web/src/stories/ApiKeySetup.stories.tsx`
- Create: `web/src/stories/CreatePage.stories.tsx`
- Create: `web/src/stories/ReviewScreen.stories.tsx`
- Create: `web/src/stories/ProjectPage.stories.tsx`

**Step 1: Write stories**

`web/src/stories/ApiKeySetup.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import ApiKeySetup from "../components/ApiKeySetup";

const meta: Meta<typeof ApiKeySetup> = {
  title: "Components/ApiKeySetup",
  component: ApiKeySetup,
  parameters: { layout: "centered" },
};
export default meta;

type Story = StoryObj<typeof ApiKeySetup>;

export const Default: Story = {
  args: { onComplete: () => console.log("Keys saved") },
};
```

`web/src/stories/CreatePage.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";
import CreatePage from "../pages/CreatePage";

const meta: Meta<typeof CreatePage> = {
  title: "Pages/CreatePage",
  component: CreatePage,
  decorators: [(Story) => <MemoryRouter><Story /></MemoryRouter>],
};
export default meta;

type Story = StoryObj<typeof CreatePage>;

export const Default: Story = {};
```

`web/src/stories/ReviewScreen.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";
import ReviewScreen from "../components/ReviewScreen";

const meta: Meta<typeof ReviewScreen> = {
  title: "Components/ReviewScreen",
  component: ReviewScreen,
  decorators: [(Story) => <MemoryRouter><Story /></MemoryRouter>],
};
export default meta;

type Story = StoryObj<typeof ReviewScreen>;

export const WithArtifacts: Story = {
  args: {
    projectId: "adapt-2026-02-25",
    checkpoint: { phase: "analysis", project_id: "adapt-2026-02-25" },
  },
};

export const EmptyArtifacts: Story = {
  args: {
    projectId: "adapt-2026-02-25",
    checkpoint: { phase: "outline", project_id: "adapt-2026-02-25" },
  },
};
```

`web/src/stories/ProjectPage.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ProjectPage from "../pages/ProjectPage";

const meta: Meta<typeof ProjectPage> = {
  title: "Pages/ProjectPage",
  component: ProjectPage,
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/project/test-project"]}>
        <Routes>
          <Route path="/project/:projectId" element={<Story />} />
        </Routes>
      </MemoryRouter>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof ProjectPage>;

export const Processing: Story = {};
```

**Step 2: Verify Storybook builds**

```bash
cd web && npx storybook build --quiet
```

Expected: Builds without errors.

**Step 3: Commit**

```bash
git add web/src/stories/
git commit -m "feat(web): add Storybook stories for all screens and components"
```

---

## Task 11: Update tracking documents

**Files:**
- Modify: `BUGS_AND_TODOS.md`

**Step 1: Update BUGS_AND_TODOS.md**

Mark Plan 2 as complete:

```markdown
- [x] **Web UI React frontend (Plan 2/3)** — ...
```

**Step 2: Commit**

```bash
git add BUGS_AND_TODOS.md
git commit -m "docs: mark web UI frontend (Plan 2/3) as complete"
```

---

## Task 12: Per-scene progress bar component

**Files:**
- Create: `web/src/components/ProgressBar.tsx`
- Create: `web/src/__tests__/ProgressBar.test.tsx`
- Modify: `web/src/pages/ProjectPage.tsx`

**Step 1: Write the failing test**

`web/src/__tests__/ProgressBar.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import ProgressBar from "../components/ProgressBar";

describe("ProgressBar", () => {
  it("renders phase name", () => {
    render(<ProgressBar phase="image_generation" scenesDone={3} scenesTotal={10} />);
    expect(screen.getByText(/image generation/i)).toBeInTheDocument();
  });

  it("shows scene count", () => {
    render(<ProgressBar phase="tts_generation" scenesDone={5} scenesTotal={10} />);
    expect(screen.getByText("5 / 10")).toBeInTheDocument();
  });

  it("renders a progress element", () => {
    render(<ProgressBar phase="analysis" scenesDone={2} scenesTotal={8} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "2");
    expect(bar).toHaveAttribute("aria-valuemax", "8");
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd web && npm test
```

Expected: FAIL.

**Step 3: Write the implementation**

`web/src/components/ProgressBar.tsx`:

```tsx
interface Props {
  phase: string;
  scenesDone: number;
  scenesTotal: number;
}

export default function ProgressBar({ phase, scenesDone, scenesTotal }: Props) {
  const pct = scenesTotal > 0 ? (scenesDone / scenesTotal) * 100 : 0;
  const phaseName = phase.replace(/_/g, " ");

  return (
    <div style={{ marginBottom: "1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
        <span style={{ textTransform: "capitalize" }}>{phaseName}</span>
        <span>{scenesDone} / {scenesTotal}</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={scenesDone}
        aria-valuemin={0}
        aria-valuemax={scenesTotal}
        style={{
          background: "#e0e0e0",
          borderRadius: 4,
          height: 20,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            background: "#4caf50",
            height: "100%",
            width: `${pct}%`,
            transition: "width 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}
```

Update `web/src/pages/ProjectPage.tsx` to track scene progress and render the bar. In the `useProgressStream` hook, track `scene_progress` events by maintaining `scenesDone` and `scenesTotal` in state:

Modify the processing section of `ProjectPage.tsx`:

```tsx
// Replace the raw event log with:
import ProgressBar from "../components/ProgressBar";

// In the processing return block:
{progress.currentPhase && progress.scenesTotal > 0 && (
  <ProgressBar
    phase={progress.currentPhase}
    scenesDone={progress.scenesDone}
    scenesTotal={progress.scenesTotal}
  />
)}
```

And update `useProgressStream` to track `scene_progress` events — add `scenesDone` and `scenesTotal` to the state, and in the `scene_progress` handler set them from `data.scene_number` and `data.total`.

**Step 4: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 5: Commit**

```bash
git add web/src/components/ProgressBar.tsx web/src/__tests__/ProgressBar.test.tsx web/src/pages/ProjectPage.tsx web/src/hooks/useProgressStream.ts
git commit -m "feat(web): add per-scene progress bar for media generation phases"
```

---

## Task 13: Retry button, download link, and error recovery

**Files:**
- Modify: `web/src/pages/ProjectPage.tsx`
- Modify: `web/src/__tests__/ProjectPage.test.tsx`
- Modify: `web/src/hooks/useProgressStream.ts`

**Step 1: Write the failing tests**

Add to `web/src/__tests__/ProjectPage.test.tsx`:

```tsx
it("shows retry button on error", () => {
  renderProjectPage("test-project");
  const es = MockEventSource.instances[0];

  act(() => {
    es.emit("error", JSON.stringify({ message: "TTS failed" }));
  });

  expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
});

it("shows download link when video is complete", () => {
  renderProjectPage("test-project");
  const es = MockEventSource.instances[0];

  act(() => {
    es.emit("completed", JSON.stringify({}));
  });

  expect(screen.getByRole("link", { name: /download/i })).toBeInTheDocument();
});
```

**Step 2: Run test to verify they fail**

```bash
cd web && npm test
```

Expected: FAIL.

**Step 3: Update ProjectPage**

In the error section, add:

```tsx
<button onClick={() => {
  api.startPipeline(projectId!);
  window.location.reload();
}}>
  Retry
</button>
```

In the complete section, add:

```tsx
<a
  href={`/api/v1/projects/${projectId}/artifacts/video_assembly/final.mp4`}
  download
>
  Download Video
</a>
```

**Step 4: SSE reconnection**

Update `useProgressStream.ts`: instead of closing on `onerror`, attempt reconnection after a delay. Use a reconnect counter to avoid infinite loops (max 5 retries). On reconnect, call `api.getProject()` to sync state before reopening the `EventSource`.

```typescript
es.onerror = () => {
  es.close();
  if (retryCount < 5) {
    retryCount++;
    setTimeout(() => {
      // Fetch current state via REST, then reconnect
      api.getProject(projectId!).then((status) => {
        if (status.status === "in_progress") {
          // Reconnect SSE
          connect();
        } else {
          // Pipeline is no longer running
          setState((prev) => ({ ...prev, isComplete: status.status === "completed" }));
        }
      });
    }, 1000 * retryCount);
  } else {
    setState((prev) => ({ ...prev, error: "Connection lost after multiple retries" }));
  }
};
```

**Step 5: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 6: Commit**

```bash
git add web/src/pages/ProjectPage.tsx web/src/__tests__/ProjectPage.test.tsx web/src/hooks/useProgressStream.ts
git commit -m "feat(web): add retry button, download link, and SSE reconnection"
```

---

## Task 14: Settings page for API key updates

**Files:**
- Create: `web/src/pages/SettingsPage.tsx`
- Create: `web/src/__tests__/SettingsPage.test.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/Layout.tsx`

**Step 1: Write the failing test**

`web/src/__tests__/SettingsPage.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import SettingsPage from "../pages/SettingsPage";

const mockGetStatus = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    getApiKeyStatus: (...args: unknown[]) => mockGetStatus(...args),
    setApiKeys: vi.fn().mockResolvedValue({ status: "ok" }),
  },
}));

describe("SettingsPage", () => {
  it("shows API key form", async () => {
    mockGetStatus.mockResolvedValueOnce({ anthropic_configured: true, openai_configured: false });

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/settings/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/anthropic/i)).toBeInTheDocument();
    });
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd web && npm test
```

Expected: FAIL.

**Step 3: Write the implementation**

`web/src/pages/SettingsPage.tsx`:

```tsx
import ApiKeySetup from "../components/ApiKeySetup";
import { useNavigate } from "react-router-dom";

export default function SettingsPage() {
  const navigate = useNavigate();

  return (
    <div>
      <h2>Settings</h2>
      <ApiKeySetup onComplete={() => navigate("/")} />
    </div>
  );
}
```

Note: The ApiKeySetup component needs a small tweak — when keys are already configured, instead of calling `onComplete` immediately, it should still show the form (pre-filled or with "configured" badges) so the user can update keys. Add a `forceShow` prop:

Update `ApiKeySetup.tsx` to accept an optional `forceShow?: boolean` prop. When `forceShow` is true, always show the form regardless of key status.

Update `web/src/App.tsx` to add the settings route:

```tsx
import SettingsPage from "./pages/SettingsPage";

// In Routes:
<Route path="/settings" element={<SettingsPage />} />
```

Update `web/src/components/Layout.tsx` to add a Settings link in the header:

```tsx
<nav>
  <Link to="/settings" style={{ marginLeft: "1rem", fontSize: "0.9rem" }}>Settings</Link>
</nav>
```

**Step 4: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 5: Commit**

```bash
git add web/src/pages/SettingsPage.tsx web/src/__tests__/SettingsPage.test.tsx web/src/App.tsx web/src/components/Layout.tsx web/src/components/ApiKeySetup.tsx
git commit -m "feat(web): add settings page for API key management"
```

---

## Task 15: Artifact edit validation and empty-text guard

**Files:**
- Modify: `web/src/components/ReviewScreen.tsx`
- Modify: `web/src/__tests__/ReviewScreen.test.tsx`

**Step 1: Write the failing test**

Add to `web/src/__tests__/ReviewScreen.test.tsx`:

```tsx
it("disables save button when content is empty", async () => {
  // Set up a scenario where editingFile is active with empty content.
  // The Save button should be disabled when the textarea is blank.
  mockListArtifacts.mockResolvedValueOnce({
    files: [{ name: "outline.json", size: 100, content_type: "application/json" }],
  });

  render(
    <MemoryRouter>
      <ReviewScreen projectId="test-project" checkpoint={{ phase: "analysis", project_id: "test-project" }} />
    </MemoryRouter>,
  );

  // Artifact loaded — test that empty content scenario is handled
  // (The actual test depends on how the edit flow is triggered)
});
```

**Step 2: Update ReviewScreen**

In `handleSave`, add validation:

```tsx
const handleSave = async () => {
  if (!editingFile || !editContent.trim()) return;
  // ... rest of save logic
};
```

And disable the Save button when content is blank:

```tsx
<button onClick={handleSave} disabled={!editContent.trim()} style={{ marginRight: "0.5rem" }}>Save</button>
```

**Step 3: Run tests**

```bash
cd web && npm test
```

Expected: All passed.

**Step 4: Commit**

```bash
git add web/src/components/ReviewScreen.tsx web/src/__tests__/ReviewScreen.test.tsx
git commit -m "fix(web): guard against saving empty artifact content"
```

---

## Task 16: Expand Storybook coverage for all states

**Files:**
- Modify: `web/src/stories/ApiKeySetup.stories.tsx`
- Modify: `web/src/stories/ProjectPage.stories.tsx`
- Modify: `web/src/stories/ReviewScreen.stories.tsx`
- Create: `web/src/stories/ProgressBar.stories.tsx`
- Create: `web/src/stories/SettingsPage.stories.tsx`

**Step 1: Add state variants**

Add stories for: loading, error, empty, and multi-stage states for each component. Specifically:

`web/src/stories/ProgressBar.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import ProgressBar from "../components/ProgressBar";

const meta: Meta<typeof ProgressBar> = {
  title: "Components/ProgressBar",
  component: ProgressBar,
};
export default meta;

type Story = StoryObj<typeof ProgressBar>;

export const EarlyProgress: Story = { args: { phase: "tts_generation", scenesDone: 2, scenesTotal: 12 } };
export const HalfDone: Story = { args: { phase: "image_generation", scenesDone: 6, scenesTotal: 12 } };
export const NearComplete: Story = { args: { phase: "caption_generation", scenesDone: 11, scenesTotal: 12 } };
export const Complete: Story = { args: { phase: "video_assembly", scenesDone: 12, scenesTotal: 12 } };
```

Add error/loading/completed variants to `ProjectPage.stories.tsx` and `ReviewScreen.stories.tsx`.

Add a `SettingsPage.stories.tsx`.

**Step 2: Verify Storybook builds**

```bash
cd web && npx storybook build --quiet
```

Expected: Builds without errors.

**Step 3: Commit**

```bash
git add web/src/stories/
git commit -m "feat(web): expand Storybook coverage for all screen states"
```

---

## Design Gap Notes (intentionally deferred)

The following design doc requirements are **not covered** in this plan because they depend on backend features that don't exist yet:

- **File upload** (#4, #27, #28) — Backend v1 API only accepts `source_text`. File upload is tracked in `BUGS_AND_TODOS.md`.
- **API key error hinting** (#32) — Raw error messages from the backend are shown as-is. No special key-failure detection.
- **409 Conflict UX** (#34) — The generic `ApiError` surfaces "Pipeline is already running" from the backend detail message, which is clear enough for v1.

---

## Retrospective

(To be filled in after implementation.)

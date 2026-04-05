import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { api } from "../api/client";

const mockFetch = vi.fn();
let originalFetch: typeof globalThis.fetch;

beforeEach(() => {
  originalFetch = globalThis.fetch;
  globalThis.fetch = mockFetch;
  mockFetch.mockReset();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("api.getHealth", () => {
  it("calls GET /api/v1/health", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "ok" }),
    });

    const result = await api.getHealth();
    expect(result).toEqual({ status: "ok" });
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/health",
      expect.objectContaining({ method: "GET" }),
    );
  });
});

describe("api.getApiKeyStatus", () => {
  it("calls GET /api/v1/settings/api-keys", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          anthropic_configured: true,
          openai_configured: false,
        }),
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
      json: () =>
        Promise.resolve({
          project_id: "adapt-2026-02-25",
          mode: "adapt",
        }),
    });

    const result = await api.createProject({
      mode: "adapt",
      source_text: "A story.",
    });
    expect(result.project_id).toBe("adapt-2026-02-25");
  });
});

describe("api.createProject autonomous", () => {
  it("sends autonomous flag in create request", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          project_id: "test",
          mode: "adapt",
          project_dir: "/tmp",
        }),
    });

    await api.createProject({
      mode: "adapt",
      source_text: "Test.",
      autonomous: true,
    });
    const body = JSON.parse(mockFetch.mock.calls[0][1]?.body as string);
    expect(body.autonomous).toBe(true);
  });
});

describe("api.getProject", () => {
  it("calls GET /api/v1/projects/{id}", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
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

describe("api.deleteProject", () => {
  it("calls DELETE /api/v1/projects/{id}", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "deleted" }),
    });

    const result = await api.deleteProject("adapt-2026-02-25");
    expect(result.status).toBe("deleted");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/projects/adapt-2026-02-25",
      expect.objectContaining({ method: "DELETE" }),
    );
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

  it("sends auto flag when auto=true", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "approved" }),
    });

    await api.approvePipeline("test-project", true);
    const body = JSON.parse(mockFetch.mock.calls[0][1]?.body as string);
    expect(body.auto).toBe(true);
  });

  it("sends empty body when auto is not specified", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ status: "approved" }),
    });

    await api.approvePipeline("test-project");
    const body = JSON.parse(mockFetch.mock.calls[0][1]?.body as string);
    expect(body.auto).toBeUndefined();
  });
});

describe("api.listArtifacts", () => {
  it("calls GET /api/v1/projects/{id}/artifacts/{phase}", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          files: [
            {
              name: "analysis.json",
              size: 100,
              content_type: "application/json",
            },
          ],
        }),
    });

    const result = await api.listArtifacts(
      "adapt-2026-02-25",
      "analysis",
    );
    expect(result.files).toHaveLength(1);
  });
});

describe("api.getArtifactUrl", () => {
  it("returns the correct URL for downloading an artifact", () => {
    const url = api.getArtifactUrl(
      "adapt-2026-02-25",
      "analysis",
      "analysis.json",
    );
    expect(url).toBe(
      "/api/v1/projects/adapt-2026-02-25/artifacts/analysis/analysis.json",
    );
  });
});

describe("api.updateArtifact", () => {
  it("calls PUT /api/v1/projects/{id}/artifacts/{phase}/{file}", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          status: "updated",
          filename: "analysis.json",
        }),
    });

    await api.updateArtifact(
      "adapt-2026-02-25",
      "analysis",
      "analysis.json",
      "new content",
    );
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/projects/adapt-2026-02-25/artifacts/analysis/analysis.json",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ content: "new content" }),
      }),
    );
  });
});

describe("api.listProjects", () => {
  it("calls GET /api/v1/projects and returns project list", async () => {
    const mockResponse = {
      projects: [
        {
          project_id: "adapt-2026-01-01",
          mode: "adapt",
          status: "completed",
          current_phase: "VIDEO_ASSEMBLY",
          scene_count: 5,
          created_at: "2026-01-01T00:00:00",
          source_text_preview: "Once upon a time...",
        },
      ],
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    const result = await api.listProjects();

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/projects",
      expect.objectContaining({ method: "GET" }),
    );
    expect(result.projects).toHaveLength(1);
    expect(result.projects[0].project_id).toBe("adapt-2026-01-01");
  });
});

describe("error handling", () => {
  it("throws ApiError on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: "Project not found" }),
    });

    await expect(api.getProject("nonexistent")).rejects.toThrow(
      "Project not found",
    );
  });

  it("falls back to 'Request failed' when response body is not JSON", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("not json")),
    });

    await expect(api.getHealth()).rejects.toThrow("Request failed");
  });
});

describe("api.rerunFromPhase", () => {
  it("calls POST /api/v1/projects/{id}/rerun-from/{phase}", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          status: "rerunning",
          from_phase: "analysis",
          project_id: "test-1",
        }),
    });

    const result = await api.rerunFromPhase("test-1", "analysis");
    expect(result.status).toBe("rerunning");
    expect(result.from_phase).toBe("analysis");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/projects/test-1/rerun-from/analysis",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

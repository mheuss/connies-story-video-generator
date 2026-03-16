import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { UnifiedProjectPage } from "../pages/UnifiedProjectPage";

vi.mock("../api/client", () => ({
  api: {
    getProject: vi.fn(),
    startPipeline: vi.fn(),
    approvePipeline: vi.fn(),
    rerunFromPhase: vi.fn(),
  },
}));

vi.mock("../hooks/useProgressStream", () => ({
  useProgressStream: vi.fn(() => ({
    currentPhase: null,
    scenesDone: 0,
    scenesTotal: 0,
    checkpoint: null,
    isComplete: false,
    error: null,
    events: [],
    reset: vi.fn(),
  })),
}));

function renderPage(projectId: string) {
  return render(
    <MemoryRouter initialEntries={[`/project/${projectId}`]}>
      <Routes>
        <Route path="/project/:projectId" element={<UnifiedProjectPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("UnifiedProjectPage - Timeline mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches project on mount and renders timeline", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "adapt-2026-03-16",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "image_prompts",
      scene_count: 5,
      created_at: "2026-03-16T10:00:00Z",
    });

    renderPage("adapt-2026-03-16");

    await waitFor(() => {
      expect(screen.getByText("Analysis")).toBeInTheDocument();
      expect(screen.getByText("Image Prompts")).toBeInTheDocument();
      expect(screen.getByText("Video Assembly")).toBeInTheDocument();
    });
  });

  it("shows loading state while fetching", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockReturnValue(new Promise(() => {}));
    renderPage("test-project");
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows error when fetch fails", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockRejectedValue(new Error("Not found"));
    renderPage("nonexistent");
    await waitFor(() => {
      expect(screen.getByText(/not found/i)).toBeInTheDocument();
    });
  });

  it("shows start pipeline button for pending project", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "pending",
      current_phase: null,
      scene_count: 0,
      created_at: "2026-03-16T10:00:00Z",
    });
    renderPage("test-1");
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /start pipeline/i })
      ).toBeInTheDocument();
    });
  });

  it("shows video player for completed project", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "completed",
      current_phase: "video_assembly",
      scene_count: 5,
      created_at: "2026-03-16T10:00:00Z",
    });
    renderPage("test-1");
    await waitFor(() => {
      expect(screen.getByText(/final video/i)).toBeInTheDocument();
    });
  });

  it("enables SSE only when project is in_progress", async () => {
    const { api } = await import("../api/client");
    const { useProgressStream } = await import("../hooks/useProgressStream");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "pending",
      current_phase: null,
      scene_count: 0,
      created_at: "2026-03-16T10:00:00Z",
    });
    renderPage("test-1");
    await waitFor(() => {
      expect(vi.mocked(useProgressStream)).toHaveBeenCalledWith(
        "test-1",
        expect.objectContaining({ enabled: false })
      );
    });
  });
});

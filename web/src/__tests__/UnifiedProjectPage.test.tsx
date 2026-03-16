import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { UnifiedProjectPage } from "../pages/UnifiedProjectPage";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("../api/client", () => ({
  api: {
    getProject: vi.fn(),
    getApiKeyStatus: vi.fn(),
    createProject: vi.fn(),
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

describe("UnifiedProjectPage - Creation mode", () => {
  async function setupApiKeysMock(configured = true) {
    const { api } = await import("../api/client");
    vi.mocked(api.getApiKeyStatus).mockResolvedValue({
      anthropic_configured: configured,
      openai_configured: configured,
      elevenlabs_configured: false,
    });
    return api;
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders creation form when projectId is 'new'", async () => {
    await setupApiKeysMock();
    renderPage("new");
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /create project/i })
      ).toBeInTheDocument();
    });
  });

  it("shows mode selector with three options", async () => {
    await setupApiKeysMock();
    renderPage("new");
    await waitFor(() => {
      const radios = screen.getAllByRole("radio");
      expect(radios).toHaveLength(3);
      expect(screen.getByLabelText(/adapt.*narrate/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/original.*write/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/inspired.*new story/i)).toBeInTheDocument();
    });
  });

  it("does not fetch project status when projectId is 'new'", async () => {
    const api = await setupApiKeysMock();
    renderPage("new");
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /create project/i })
      ).toBeInTheDocument();
    });
    expect(api.getProject).not.toHaveBeenCalled();
  });

  it("shows API key setup when keys are not configured", async () => {
    await setupApiKeysMock(false);
    renderPage("new");
    await waitFor(() => {
      expect(screen.getByText(/api key/i)).toBeInTheDocument();
    });
  });

  it("changes source text label based on mode", async () => {
    await setupApiKeysMock();
    const user = userEvent.setup();
    renderPage("new");

    // Default mode is adapt
    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
    });

    // Switch to original mode
    await user.click(screen.getByLabelText(/original/i));
    expect(screen.getByLabelText(/topic or idea/i)).toBeInTheDocument();
  });

  it("disables submit button when source text is empty", async () => {
    await setupApiKeysMock();
    renderPage("new");
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /create project/i })
      ).toBeDisabled();
    });
  });

  it("enables submit button when source text is provided", async () => {
    await setupApiKeysMock();
    const user = userEvent.setup();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/story to adapt/i), "Once upon a time");
    expect(
      screen.getByRole("button", { name: /create project/i })
    ).toBeEnabled();
  });

  it("creates project and navigates on submit without starting pipeline", async () => {
    const api = await setupApiKeysMock();
    vi.mocked(api.createProject).mockResolvedValue({
      project_id: "adapt-2026-03-16",
      mode: "adapt",
      project_dir: "/tmp/adapt-2026-03-16",
    });

    const user = userEvent.setup();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/story to adapt/i), "A test story");
    await user.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() => {
      expect(api.createProject).toHaveBeenCalledWith({
        mode: "adapt",
        source_text: "A test story",
        autonomous: false,
      });
    });

    expect(api.startPipeline).not.toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith("/project/adapt-2026-03-16", {
      replace: true,
    });
  });

  it("shows error on submission failure without clearing input", async () => {
    const api = await setupApiKeysMock();
    vi.mocked(api.createProject).mockRejectedValue(
      new Error("Server error")
    );

    const user = userEvent.setup();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/story to adapt/i), "A test story");
    await user.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/server error/i);
    });

    // Input should not be cleared
    expect(screen.getByLabelText(/story to adapt/i)).toHaveValue("A test story");
  });

  it("sends autonomous flag when checkbox is checked", async () => {
    const api = await setupApiKeysMock();
    vi.mocked(api.createProject).mockResolvedValue({
      project_id: "adapt-2026-03-16",
      mode: "adapt",
      project_dir: "/tmp/adapt-2026-03-16",
    });

    const user = userEvent.setup();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/story to adapt/i), "A test story");
    await user.click(screen.getByLabelText(/run to completion/i));
    await user.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() => {
      expect(api.createProject).toHaveBeenCalledWith({
        mode: "adapt",
        source_text: "A test story",
        autonomous: true,
      });
    });
  });

  it("has visible labels for all form fields", async () => {
    await setupApiKeysMock();
    renderPage("new");

    await waitFor(() => {
      // Mode selector has a visible group label
      expect(screen.getByText(/mode/i)).toBeInTheDocument();
      // Source text has a visible label
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
      // Autonomous has a visible label
      expect(screen.getByLabelText(/run to completion/i)).toBeInTheDocument();
    });
  });

  it("marks required fields visually", async () => {
    await setupApiKeysMock();
    renderPage("new");

    await waitFor(() => {
      // Required indicator on source text label
      const sourceLabel = screen.getByText(/story to adapt/i);
      expect(sourceLabel.closest("label")).toHaveTextContent(/\*/);
    });
  });
});

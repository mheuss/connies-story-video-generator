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
    listArtifacts: vi.fn().mockResolvedValue({ files: [] }),
    getArtifactUrl: vi.fn().mockReturnValue("/mock-artifact-url"),
    updateArtifact: vi.fn(),
    getTtsScenes: vi.fn().mockResolvedValue({ scenes: [] }),
    updateNarrationText: vi.fn(),
    regenerateTtsScene: vi.fn(),
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

  it("shows file drop zone in adapt mode", async () => {
    await setupApiKeysMock();
    renderPage("new");
    await waitFor(() => {
      expect(screen.getByText(/drop a text file here/i)).toBeInTheDocument();
    });
  });

  it("does not show file drop zone in original mode", async () => {
    await setupApiKeysMock();
    const user = userEvent.setup();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/adapt.*narrate/i)).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText(/original/i));
    expect(
      screen.queryByText(/drop a text file here/i)
    ).not.toBeInTheDocument();
  });

  it("does not show file drop zone in inspired_by mode", async () => {
    await setupApiKeysMock();
    const user = userEvent.setup();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/adapt.*narrate/i)).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText(/inspired by/i));
    expect(
      screen.queryByText(/drop a text file here/i)
    ).not.toBeInTheDocument();
  });

  it("populates textarea when file is loaded via drop zone", async () => {
    await setupApiKeysMock();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
    });

    // Simulate file selection via the hidden input
    const input = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    const file = new File(["A tale of two cities"], "tale.txt", {
      type: "text/plain",
    });
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toHaveValue(
        "A tale of two cities"
      );
    });
    // Filename should be shown
    expect(screen.getByText("tale.txt")).toBeInTheDocument();
  });

  it("clears textarea and filename when remove is clicked", async () => {
    await setupApiKeysMock();
    const user = userEvent.setup();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
    });

    // Load a file
    const input = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    const file = new File(["Story content"], "story.txt", {
      type: "text/plain",
    });
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText("story.txt")).toBeInTheDocument();
    });

    // Click remove
    await user.click(screen.getByRole("button", { name: /remove/i }));

    // Textarea should be empty and drop zone should reappear
    expect(screen.getByLabelText(/story to adapt/i)).toHaveValue("");
    expect(screen.getByText(/drop a text file here/i)).toBeInTheDocument();
  });

  it("clears filename when switching away from adapt mode", async () => {
    await setupApiKeysMock();
    const user = userEvent.setup();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
    });

    // Load a file in adapt mode
    const input = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    const file = new File(["Story content"], "story.txt", {
      type: "text/plain",
    });
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText("story.txt")).toBeInTheDocument();
    });

    // Switch to original mode
    await user.click(screen.getByLabelText(/original.*write/i));

    // Switch back to adapt mode
    await user.click(screen.getByLabelText(/adapt.*narrate/i));

    // Drop zone should appear (not the filename badge)
    expect(screen.getByText(/drop a text file here/i)).toBeInTheDocument();
    expect(screen.queryByText("story.txt")).not.toBeInTheDocument();
  });

  it("submits file content via existing API call", async () => {
    const api = await setupApiKeysMock();
    vi.mocked(api.createProject).mockResolvedValue({
      project_id: "adapt-2026-03-25",
      mode: "adapt",
      project_dir: "/tmp/adapt-2026-03-25",
    });

    const user = userEvent.setup();
    renderPage("new");

    await waitFor(() => {
      expect(screen.getByLabelText(/story to adapt/i)).toBeInTheDocument();
    });

    // Load a file
    const input = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    const file = new File(["File story content"], "story.txt", {
      type: "text/plain",
    });
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText("story.txt")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() => {
      expect(api.createProject).toHaveBeenCalledWith({
        mode: "adapt",
        source_text: "File story content",
        autonomous: false,
      });
    });
  });
});

describe("UnifiedProjectPage - Edit and re-run", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows approve buttons on checkpoint phase", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "image_prompts",
      scene_count: 5,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.listArtifacts).mockResolvedValue({ files: [] });

    renderPage("test-1");

    await waitFor(() => {
      expect(screen.getByText("Image Prompts")).toBeInTheDocument();
    });

    // The checkpoint phase (image_prompts) should show approve buttons
    expect(
      screen.getByRole("button", { name: /approve & continue/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /auto-approve remaining/i })
    ).toBeInTheDocument();
  });

  it("calls approvePipeline when approve button is clicked", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "image_prompts",
      scene_count: 5,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.listArtifacts).mockResolvedValue({ files: [] });
    vi.mocked(api.approvePipeline).mockResolvedValue({ status: "ok" });

    const user = userEvent.setup();
    renderPage("test-1");

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /approve & continue/i })
      ).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: /approve & continue/i })
    );

    await waitFor(() => {
      expect(api.approvePipeline).toHaveBeenCalledWith("test-1", undefined);
    });
  });

  it("calls approvePipeline with auto flag when auto-approve is clicked", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "image_prompts",
      scene_count: 5,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.listArtifacts).mockResolvedValue({ files: [] });
    vi.mocked(api.approvePipeline).mockResolvedValue({ status: "ok" });

    const user = userEvent.setup();
    renderPage("test-1");

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /auto-approve remaining/i })
      ).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: /auto-approve remaining/i })
    );

    await waitFor(() => {
      expect(api.approvePipeline).toHaveBeenCalledWith("test-1", true);
    });
  });

  it("does not show approve buttons on completed (non-checkpoint) phases", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "image_prompts",
      scene_count: 5,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.listArtifacts).mockResolvedValue({ files: [] });

    renderPage("test-1");

    await waitFor(() => {
      expect(screen.getByText("Image Prompts")).toBeInTheDocument();
    });

    // Only one set of approve buttons should exist (for the checkpoint phase)
    const approveButtons = screen.getAllByRole("button", {
      name: /approve & continue/i,
    });
    expect(approveButtons).toHaveLength(1);
  });

  it("loads artifacts for the checkpoint phase immediately", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "image_prompts",
      scene_count: 5,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.listArtifacts).mockResolvedValue({ files: [] });

    renderPage("test-1");

    await waitFor(() => {
      expect(screen.getByText("Image Prompts")).toBeInTheDocument();
    });

    // The checkpoint phase (image_prompts) is always expanded, so its
    // ArtifactViewer mounts immediately and fetches artifacts
    await waitFor(() => {
      expect(api.listArtifacts).toHaveBeenCalledWith("test-1", "image_prompts");
    });
  });

  it("loads artifacts for completed phase when expanded", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "image_prompts",
      scene_count: 5,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.listArtifacts).mockResolvedValue({ files: [] });

    const user = userEvent.setup();
    renderPage("test-1");

    await waitFor(() => {
      expect(screen.getByText("Analysis")).toBeInTheDocument();
    });

    // Completed phases are collapsed by default. Expand the Analysis phase.
    await user.click(
      screen.getByRole("button", { name: /analysis phase, completed/i })
    );

    // Now the ArtifactViewer inside Analysis should mount and fetch artifacts
    await waitFor(() => {
      expect(api.listArtifacts).toHaveBeenCalledWith("test-1", "analysis");
    });
  });
});

describe("UnifiedProjectPage - TTS integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders TtsReviewPanel for tts_generation checkpoint", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "tts_generation",
      scene_count: 3,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.getTtsScenes).mockResolvedValue({
      scenes: [
        {
          scene_number: 1,
          title: "Scene 1",
          narration_text: "Hello",
          audio_file: "scene_001.mp3",
          audio_url: "/audio/1.mp3",
          has_audio: true,
        },
      ],
    });

    renderPage("test-1");

    await waitFor(() => {
      // TtsReviewPanel content should be visible
      expect(screen.getByText("Scene 1: Scene 1")).toBeInTheDocument();
    });

    // Approve buttons should also be present since it's a checkpoint
    expect(
      screen.getByRole("button", { name: /approve & continue/i }),
    ).toBeInTheDocument();
  });

  it("renders TtsReviewPanel instead of ArtifactViewer for tts_generation", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "tts_generation",
      scene_count: 3,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.getTtsScenes).mockResolvedValue({
      scenes: [
        {
          scene_number: 1,
          title: "The Lighthouse",
          narration_text: "A beam of light swept across the dark sea.",
          audio_file: "scene_001.mp3",
          audio_url: "/audio/1.mp3",
          has_audio: true,
        },
      ],
    });

    renderPage("test-1");

    await waitFor(() => {
      expect(
        screen.getByText("Scene 1: The Lighthouse"),
      ).toBeInTheDocument();
    });

    // TTS panel uses getTtsScenes, NOT listArtifacts for tts_generation
    expect(api.getTtsScenes).toHaveBeenCalledWith("test-1");
    expect(api.listArtifacts).not.toHaveBeenCalledWith(
      "test-1",
      "tts_generation",
    );
  });

  it("shows approve buttons for tts_generation checkpoint", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "tts_generation",
      scene_count: 3,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.getTtsScenes).mockResolvedValue({ scenes: [] });

    renderPage("test-1");

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /approve & continue/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /auto-approve remaining/i }),
      ).toBeInTheDocument();
    });
  });

  it("renders TtsReviewPanel for completed tts_generation when expanded", async () => {
    const { api } = await import("../api/client");
    // Project has progressed past tts_generation so it's completed
    vi.mocked(api.getProject).mockResolvedValue({
      project_id: "test-1",
      mode: "adapt",
      status: "awaiting_review",
      current_phase: "image_generation",
      scene_count: 3,
      created_at: "2026-03-16T10:00:00Z",
    });
    vi.mocked(api.getTtsScenes).mockResolvedValue({
      scenes: [
        {
          scene_number: 1,
          title: "The Storm",
          narration_text: "Wind howled through the tower.",
          audio_file: "scene_001.mp3",
          audio_url: "/audio/1.mp3",
          has_audio: true,
        },
      ],
    });

    const user = userEvent.setup();
    renderPage("test-1");

    await waitFor(() => {
      expect(screen.getByText("TTS Generation")).toBeInTheDocument();
    });

    // tts_generation is completed and collapsed by default. Expand it.
    await user.click(
      screen.getByRole("button", {
        name: /tts generation phase, completed/i,
      }),
    );

    // TtsReviewPanel should load its scenes
    await waitFor(() => {
      expect(api.getTtsScenes).toHaveBeenCalledWith("test-1");
    });

    await waitFor(() => {
      expect(screen.getByText("Scene 1: The Storm")).toBeInTheDocument();
    });
  });
});

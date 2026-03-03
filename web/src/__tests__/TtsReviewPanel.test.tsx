import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import TtsReviewPanel from "../components/TtsReviewPanel";

const mockGetTtsScenes = vi.fn();
const mockRegenerateTtsScene = vi.fn();
const mockUpdateNarrationText = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    getTtsScenes: (...args: unknown[]) => mockGetTtsScenes(...args),
    regenerateTtsScene: (...args: unknown[]) => mockRegenerateTtsScene(...args),
    updateNarrationText: (...args: unknown[]) => mockUpdateNarrationText(...args),
  },
}));

const mockScenes = {
  scenes: [
    {
      scene_number: 1,
      title: "The Storm",
      narration_text: "The lighthouse keeper watched the waves crash.",
      audio_file: "scene_001.mp3",
      audio_url: "/api/v1/projects/test-project/artifacts/tts_generation/scene_001.mp3",
      has_audio: true,
    },
    {
      scene_number: 2,
      title: "The Calm",
      narration_text: "Morning came quietly over the sea.",
      audio_file: "scene_002.mp3",
      audio_url: "/api/v1/projects/test-project/artifacts/tts_generation/scene_002.mp3",
      has_audio: false,
    },
  ],
};

describe("TtsReviewPanel", () => {
  beforeEach(() => {
    mockGetTtsScenes.mockReset();
    mockRegenerateTtsScene.mockReset();
    mockUpdateNarrationText.mockReset();
  });

  it("renders loading state then scene cards", async () => {
    mockGetTtsScenes.mockResolvedValueOnce(mockScenes);

    render(<TtsReviewPanel projectId="test-project" />);

    expect(screen.getByText("Loading audio scenes...")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Scene 1: The Storm")).toBeInTheDocument();
      expect(screen.getByText("Scene 2: The Calm")).toBeInTheDocument();
    });

    expect(screen.queryByText("Loading audio scenes...")).not.toBeInTheDocument();
  });

  it("renders an audio element for a scene with audio", async () => {
    mockGetTtsScenes.mockResolvedValueOnce(mockScenes);

    render(<TtsReviewPanel projectId="test-project" />);

    await waitFor(() => {
      expect(screen.getByText("Scene 1: The Storm")).toBeInTheDocument();
    });

    // The component renders <audio controls src="..."> for scenes with has_audio: true
    const audioElements = document.querySelectorAll("audio");
    expect(audioElements.length).toBe(1);
    expect(audioElements[0].getAttribute("src")).toBe(
      "/api/v1/projects/test-project/artifacts/tts_generation/scene_001.mp3",
    );
  });

  it("shows 'No audio generated' for a scene without audio", async () => {
    mockGetTtsScenes.mockResolvedValueOnce(mockScenes);

    render(<TtsReviewPanel projectId="test-project" />);

    await waitFor(() => {
      expect(screen.getByText("Scene 2: The Calm")).toBeInTheDocument();
    });

    expect(screen.getByText("No audio generated")).toBeInTheDocument();

    // Only one audio element (for scene 1), not two
    const audioElements = document.querySelectorAll("audio");
    expect(audioElements.length).toBe(1);
  });

  it("toggles narration text visibility with Show/Hide text button", async () => {
    mockGetTtsScenes.mockResolvedValueOnce(mockScenes);
    const user = userEvent.setup();

    render(<TtsReviewPanel projectId="test-project" />);

    await waitFor(() => {
      expect(screen.getByText("Scene 1: The Storm")).toBeInTheDocument();
    });

    const showButtons = screen.getAllByText("Show text");
    expect(showButtons.length).toBe(2);

    // Click "Show text" for scene 1
    await user.click(showButtons[0]);

    // Narration text should now be visible in a textarea
    const textarea = screen.getByDisplayValue(
      "The lighthouse keeper watched the waves crash.",
    );
    expect(textarea).toBeInTheDocument();
    expect(textarea.tagName).toBe("TEXTAREA");

    // Button should now say "Hide text"
    expect(screen.getByText("Hide text")).toBeInTheDocument();

    // Click "Hide text" to collapse
    await user.click(screen.getByText("Hide text"));

    // Textarea should be gone
    expect(
      screen.queryByDisplayValue("The lighthouse keeper watched the waves crash."),
    ).not.toBeInTheDocument();
  });

  it("allows editing and saving narration text", async () => {
    mockGetTtsScenes.mockResolvedValueOnce(mockScenes);

    const updatedScene = {
      ...mockScenes.scenes[0],
      narration_text: "Updated narration text.",
    };
    mockUpdateNarrationText.mockResolvedValueOnce(updatedScene);

    const user = userEvent.setup();

    render(<TtsReviewPanel projectId="test-project" />);

    await waitFor(() => {
      expect(screen.getByText("Scene 1: The Storm")).toBeInTheDocument();
    });

    // Expand scene 1 text
    const showButtons = screen.getAllByText("Show text");
    await user.click(showButtons[0]);

    // Click Edit
    await user.click(screen.getByText("Edit"));

    // Textarea should now be editable - clear it and type new text
    const textarea = screen.getByDisplayValue(
      "The lighthouse keeper watched the waves crash.",
    );
    await user.clear(textarea);
    await user.type(textarea, "Updated narration text.");

    // Click Save
    await user.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(mockUpdateNarrationText).toHaveBeenCalledWith(
        "test-project",
        1,
        "Updated narration text.",
      );
    });
  });

  it("calls regenerateTtsScene when Regenerate is clicked", async () => {
    mockGetTtsScenes.mockResolvedValueOnce(mockScenes);

    const updatedScene = {
      ...mockScenes.scenes[0],
      audio_url: "/api/v1/projects/test-project/artifacts/tts_generation/scene_001_v2.mp3",
    };
    mockRegenerateTtsScene.mockResolvedValueOnce(updatedScene);

    const user = userEvent.setup();

    render(<TtsReviewPanel projectId="test-project" />);

    await waitFor(() => {
      expect(screen.getByText("Scene 1: The Storm")).toBeInTheDocument();
    });

    // Click Regenerate for scene 1 (first Regenerate button)
    const regenerateButtons = screen.getAllByText("Regenerate");
    await user.click(regenerateButtons[0]);

    await waitFor(() => {
      expect(mockRegenerateTtsScene).toHaveBeenCalledWith("test-project", 1);
    });
  });

  it("shows 'No audio generated' and no audio element for scene without audio", async () => {
    // Render with only the scene that has no audio
    mockGetTtsScenes.mockResolvedValueOnce({
      scenes: [mockScenes.scenes[1]],
    });

    render(<TtsReviewPanel projectId="test-project" />);

    await waitFor(() => {
      expect(screen.getByText("Scene 2: The Calm")).toBeInTheDocument();
    });

    expect(screen.getByText("No audio generated")).toBeInTheDocument();

    // No audio elements at all
    const audioElements = document.querySelectorAll("audio");
    expect(audioElements.length).toBe(0);
  });

  it("shows an error message when fetching scenes fails", async () => {
    mockGetTtsScenes.mockRejectedValueOnce(new Error("Network error"));

    render(<TtsReviewPanel projectId="test-project" />);

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });

    // Loading should be gone
    expect(screen.queryByText("Loading audio scenes...")).not.toBeInTheDocument();
  });
});

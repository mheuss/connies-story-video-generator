import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArtifactViewer } from "../components/ArtifactViewer";

const mockListArtifacts = vi.fn();
const mockGetArtifactUrl = vi.fn();
const mockGetArtifactText = vi.fn();
const mockUpdateArtifact = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    listArtifacts: (...args: unknown[]) => mockListArtifacts(...args),
    getArtifactUrl: (...args: unknown[]) => mockGetArtifactUrl(...args),
    getArtifactText: (...args: unknown[]) => mockGetArtifactText(...args),
    updateArtifact: (...args: unknown[]) => mockUpdateArtifact(...args),
  },
}));

describe("ArtifactViewer", () => {
  beforeEach(() => {
    mockListArtifacts.mockReset();
    mockGetArtifactUrl.mockReset();
    mockGetArtifactText.mockReset();
    mockUpdateArtifact.mockReset();
  });

  it("fetches and displays artifact filenames", async () => {
    mockListArtifacts.mockResolvedValue({
      files: [
        {
          name: "analysis.json",
          size: 1024,
          content_type: "application/json",
        },
        { name: "source_story.txt", size: 512, content_type: "text/plain" },
      ],
    });

    render(
      <ArtifactViewer projectId="test" phase="analysis" editable={true} />,
    );

    await waitFor(() => {
      expect(screen.getByText("analysis.json")).toBeInTheDocument();
      expect(screen.getByText("source_story.txt")).toBeInTheDocument();
    });
  });

  it("shows edit button for text files when editable", async () => {
    mockListArtifacts.mockResolvedValue({
      files: [
        { name: "scene_001.md", size: 256, content_type: "text/markdown" },
      ],
    });

    render(
      <ArtifactViewer
        projectId="test"
        phase="scene_prose"
        editable={true}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /edit/i }),
      ).toBeInTheDocument();
    });
  });

  it("does not show edit button when not editable", async () => {
    mockListArtifacts.mockResolvedValue({
      files: [
        { name: "scene_001.md", size: 256, content_type: "text/markdown" },
      ],
    });

    render(
      <ArtifactViewer
        projectId="test"
        phase="scene_prose"
        editable={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("scene_001.md")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: /edit/i }),
    ).not.toBeInTheDocument();
  });

  it("renders image artifacts as thumbnails", async () => {
    mockListArtifacts.mockResolvedValue({
      files: [
        { name: "scene_001.png", size: 50000, content_type: "image/png" },
      ],
    });
    mockGetArtifactUrl.mockReturnValue(
      "/api/v1/projects/test/artifacts/image_generation/scene_001.png",
    );

    render(
      <ArtifactViewer
        projectId="test"
        phase="image_generation"
        editable={false}
      />,
    );

    await waitFor(() => {
      const img = screen.getByRole("img");
      expect(img).toHaveAttribute(
        "src",
        expect.stringContaining("scene_001.png"),
      );
      expect(img).toHaveAttribute(
        "alt",
        expect.stringContaining("scene_001.png"),
      );
    });
  });

  it("renders audio artifacts with audio player", async () => {
    mockListArtifacts.mockResolvedValue({
      files: [
        { name: "scene_001.mp3", size: 100000, content_type: "audio/mpeg" },
      ],
    });
    mockGetArtifactUrl.mockReturnValue(
      "/api/v1/projects/test/artifacts/tts_generation/scene_001.mp3",
    );

    render(
      <ArtifactViewer
        projectId="test"
        phase="tts_generation"
        editable={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("scene_001.mp3")).toBeInTheDocument();
      const audio = document.querySelector("audio");
      expect(audio).toBeInTheDocument();
    });
  });

  it("calls onEdited after saving an edit", async () => {
    const onEdited = vi.fn();
    mockListArtifacts.mockResolvedValue({
      files: [
        { name: "analysis.json", size: 256, content_type: "text/plain" },
      ],
    });
    mockUpdateArtifact.mockResolvedValue({
      status: "updated",
      filename: "analysis.json",
    });
    mockGetArtifactText.mockResolvedValue("original content");

    const user = userEvent.setup();
    render(
      <ArtifactViewer
        projectId="test"
        phase="analysis"
        editable={true}
        onEdited={onEdited}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /edit/i }),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /edit/i }));

    await waitFor(() => {
      expect(mockGetArtifactText).toHaveBeenCalledWith(
        "test",
        "analysis",
        "analysis.json",
      );
    });

    const textarea = screen.getByRole("textbox");
    await user.clear(textarea);
    await user.type(textarea, "updated content");

    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(mockUpdateArtifact).toHaveBeenCalledWith(
        "test",
        "analysis",
        "analysis.json",
        "updated content",
      );
      expect(onEdited).toHaveBeenCalledWith("analysis");
    });
  });

  it("shows loading state while fetching artifacts", () => {
    mockListArtifacts.mockReturnValue(new Promise(() => {}));
    render(
      <ArtifactViewer projectId="test" phase="analysis" editable={true} />,
    );
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows a validation error returned during save", async () => {
    mockListArtifacts.mockResolvedValue({
      files: [
        { name: "analysis.json", size: 256, content_type: "application/json" },
      ],
    });
    mockGetArtifactText.mockResolvedValue('{"craft_notes":"original"}');
    mockUpdateArtifact.mockRejectedValue(new Error("Content must be valid JSON"));

    const user = userEvent.setup();
    render(
      <ArtifactViewer projectId="test" phase="analysis" editable={true} />,
    );

    await user.click(await screen.findByRole("button", { name: /edit/i }));

    const textarea = await screen.findByRole("textbox");
    await user.clear(textarea);
    await user.click(textarea);
    await user.paste('{"craft_notes":"broken"');
    await user.click(screen.getByRole("button", { name: /save/i }));

    expect(await screen.findByText("Content must be valid JSON")).toBeInTheDocument();
    expect(mockUpdateArtifact).toHaveBeenCalledWith(
      "test",
      "analysis",
      "analysis.json",
      '{"craft_notes":"broken"',
    );
  });
});

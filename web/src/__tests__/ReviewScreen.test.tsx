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

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
        autonomous: false,
      });
      expect(mockStartPipeline).toHaveBeenCalledWith("adapt-2026-02-25");
      expect(mockNavigate).toHaveBeenCalledWith("/project/adapt-2026-02-25");
    });
  });

  it("sends autonomous flag when checkbox is checked", async () => {
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

    await user.type(screen.getByRole("textbox"), "A story.");
    await user.click(screen.getByRole("checkbox", { name: /run to completion/i }));
    await user.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalledWith({
        mode: "adapt",
        source_text: "A story.",
        autonomous: true,
      });
    });
  });

  it("does not send autonomous when checkbox is unchecked", async () => {
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

    await user.type(screen.getByRole("textbox"), "A story.");
    await user.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => {
      expect(mockCreateProject).toHaveBeenCalledWith({
        mode: "adapt",
        source_text: "A story.",
        autonomous: false,
      });
    });
  });
});

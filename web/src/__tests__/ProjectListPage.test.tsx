import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ProjectListPage from "../pages/ProjectListPage";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: {
    listProjects: vi.fn(),
  },
}));

const mockListProjects = vi.mocked(api.listProjects);

function renderPage() {
  return render(
    <MemoryRouter>
      <ProjectListPage />
    </MemoryRouter>,
  );
}

describe("ProjectListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state initially", () => {
    mockListProjects.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows empty state with create CTA when no projects", async () => {
    mockListProjects.mockResolvedValue({ projects: [] });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/create your first project/i)).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: /create/i });
    expect(link).toHaveAttribute("href", "/create");
  });

  it("renders project cards with correct data", async () => {
    mockListProjects.mockResolvedValue({
      projects: [
        {
          project_id: "adapt-2026-01-01",
          mode: "adapt",
          status: "completed",
          current_phase: "VIDEO_ASSEMBLY",
          scene_count: 12,
          created_at: "2026-01-01T00:00:00",
          source_text_preview: "The lighthouse keeper climbed...",
        },
      ],
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("adapt")).toBeInTheDocument();
    });
    expect(screen.getByText(/completed/i)).toBeInTheDocument();
    expect(screen.getByText(/12 scenes/i)).toBeInTheDocument();
    expect(screen.getByText(/lighthouse keeper/i)).toBeInTheDocument();
  });

  it("renders project card as link to project page", async () => {
    mockListProjects.mockResolvedValue({
      projects: [
        {
          project_id: "adapt-2026-01-01",
          mode: "adapt",
          status: "completed",
          current_phase: null,
          scene_count: 5,
          created_at: "2026-01-01T00:00:00",
          source_text_preview: "A story.",
        },
      ],
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("adapt")).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: /adapt/i });
    expect(link).toHaveAttribute("href", "/project/adapt-2026-01-01");
  });

  it("shows create new button when projects exist", async () => {
    mockListProjects.mockResolvedValue({
      projects: [
        {
          project_id: "adapt-2026-01-01",
          mode: "adapt",
          status: "pending",
          current_phase: null,
          scene_count: 0,
          created_at: "2026-01-01T00:00:00",
          source_text_preview: "A story.",
        },
      ],
    });
    renderPage();

    await waitFor(() => {
      const link = screen.getByRole("link", { name: /create new/i });
      expect(link).toHaveAttribute("href", "/create");
    });
  });

  it("shows error state when API call fails", async () => {
    mockListProjects.mockRejectedValue(new Error("Network error"));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });
  });
});

import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";

vi.mock("../api/client", () => ({
  api: {
    getApiKeyStatus: vi.fn().mockResolvedValue({ anthropic_configured: false, openai_configured: false }),
    setApiKeys: vi.fn(),
    listProjects: vi.fn().mockResolvedValue({ projects: [] }),
  },
}));

describe("Layout", () => {
  it("renders the app title", async () => {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>,
      );
    });
    expect(screen.getByText("Story Video")).toBeInTheDocument();
  });

  it("shows project list page at root route", async () => {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>,
      );
    });
    await waitFor(() => {
      expect(screen.getByText("No projects yet")).toBeInTheDocument();
    });
  });
});

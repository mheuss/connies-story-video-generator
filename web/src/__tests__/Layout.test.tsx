import { render, screen, waitFor } from "@testing-library/react";
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
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Story Video")).toBeInTheDocument();
  });

  it("shows project list page at root route", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("No projects yet")).toBeInTheDocument();
    });
  });
});

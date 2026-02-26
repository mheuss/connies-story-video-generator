import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";

vi.mock("../api/client", () => ({
  api: {
    getApiKeyStatus: vi.fn().mockResolvedValue({ anthropic_configured: false, openai_configured: false }),
    setApiKeys: vi.fn(),
  },
}));

describe("Layout", () => {
  it("renders the app title", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("Story Video")).toBeInTheDocument();
  });

  it("shows create page at root route", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/api key setup/i)).toBeInTheDocument();
    });
  });
});

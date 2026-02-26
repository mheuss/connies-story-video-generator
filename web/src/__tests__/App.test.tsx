import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";

vi.mock("../api/client", () => ({
  api: {
    getApiKeyStatus: vi.fn().mockResolvedValue({ anthropic_configured: false, openai_configured: false }),
    setApiKeys: vi.fn(),
  },
}));

describe("App", () => {
  it("renders the heading", () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("Story Video")).toBeInTheDocument();
  });
});

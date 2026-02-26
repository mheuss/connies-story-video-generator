import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import SettingsPage from "../pages/SettingsPage";

const mockGetStatus = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    getApiKeyStatus: (...args: unknown[]) => mockGetStatus(...args),
    setApiKeys: vi.fn().mockResolvedValue({ status: "ok" }),
  },
}));

describe("SettingsPage", () => {
  it("shows API key form", async () => {
    mockGetStatus.mockResolvedValueOnce({ anthropic_configured: true, openai_configured: false });

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/settings/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/anthropic/i)).toBeInTheDocument();
    });
  });
});

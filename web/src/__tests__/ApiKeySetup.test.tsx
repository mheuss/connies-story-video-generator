import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ApiKeySetup from "../components/ApiKeySetup";

const mockGetStatus = vi.fn();
const mockSetKeys = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    getApiKeyStatus: (...args: unknown[]) => mockGetStatus(...args),
    setApiKeys: (...args: unknown[]) => mockSetKeys(...args),
  },
}));

describe("ApiKeySetup", () => {
  beforeEach(() => {
    mockGetStatus.mockReset();
    mockSetKeys.mockReset();
  });

  it("shows form when keys are not configured", async () => {
    mockGetStatus.mockResolvedValueOnce({
      anthropic_configured: false,
      openai_configured: false,
    });

    render(<ApiKeySetup onComplete={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByLabelText(/anthropic/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/openai/i)).toBeInTheDocument();
    });
  });

  it("calls onComplete when keys are already configured", async () => {
    mockGetStatus.mockResolvedValueOnce({
      anthropic_configured: true,
      openai_configured: true,
    });
    const onComplete = vi.fn();

    render(<ApiKeySetup onComplete={onComplete} />);

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalled();
    });
  });

  it("submits keys and calls onComplete", async () => {
    mockGetStatus.mockResolvedValueOnce({
      anthropic_configured: false,
      openai_configured: false,
    });
    mockSetKeys.mockResolvedValueOnce({ status: "ok" });
    const onComplete = vi.fn();
    const user = userEvent.setup();

    render(<ApiKeySetup onComplete={onComplete} />);

    await waitFor(() => {
      expect(screen.getByLabelText(/anthropic/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/anthropic/i), "sk-ant-test");
    await user.type(screen.getByLabelText(/openai/i), "sk-test");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(mockSetKeys).toHaveBeenCalledWith({
        anthropic_api_key: "sk-ant-test",
        openai_api_key: "sk-test",
      });
      expect(onComplete).toHaveBeenCalled();
    });
  });

  it("keeps submit disabled until both required keys are available", async () => {
    mockGetStatus.mockResolvedValueOnce({
      anthropic_configured: false,
      openai_configured: false,
      elevenlabs_configured: false,
    });
    const user = userEvent.setup();

    render(<ApiKeySetup onComplete={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
    });

    await user.type(screen.getByLabelText(/anthropic/i), "sk-ant-test");
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();

    await user.type(screen.getByLabelText(/openai/i), "sk-openai-test");
    expect(screen.getByRole("button", { name: /save/i })).toBeEnabled();
  });

  it("allows submit when one required key is already configured and the other is entered", async () => {
    mockGetStatus.mockResolvedValueOnce({
      anthropic_configured: true,
      openai_configured: false,
      elevenlabs_configured: false,
    });
    const user = userEvent.setup();

    render(<ApiKeySetup onComplete={vi.fn()} forceShow />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
    });

    await user.type(screen.getByLabelText(/openai/i), "sk-openai-test");
    expect(screen.getByRole("button", { name: /save/i })).toBeEnabled();
  });
});

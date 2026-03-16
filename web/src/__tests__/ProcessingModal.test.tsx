import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProcessingModal } from "../components/ProcessingModal";

describe("ProcessingModal", () => {
  it("shows spinner and phase status text when open", () => {
    render(
      <ProcessingModal
        open={true}
        phase="tts_generation"
        statusText="Generating audio for scene 3 of 8"
      />,
    );
    expect(
      screen.getByText("Generating audio for scene 3 of 8"),
    ).toBeInTheDocument();
    expect(screen.getByText("TTS Generation")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <ProcessingModal open={false} phase="analysis" statusText="Working..." />,
    );
    expect(screen.queryByText("Working...")).not.toBeInTheDocument();
  });

  it("shows error state with retry and close buttons", async () => {
    const onRetry = vi.fn();
    const onClose = vi.fn();
    render(
      <ProcessingModal
        open={true}
        phase="image_generation"
        error="API rate limit exceeded"
        onRetry={onRetry}
        onClose={onClose}
      />,
    );
    expect(screen.getByText("API rate limit exceeded")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("has accessible spinner with role=status", () => {
    render(
      <ProcessingModal
        open={true}
        phase="analysis"
        statusText="Analyzing..."
      />,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("has aria-live region for status text updates", () => {
    render(
      <ProcessingModal
        open={true}
        phase="tts_generation"
        statusText="Generating audio for scene 1 of 5"
      />,
    );
    const liveRegion = screen.getByText(
      "Generating audio for scene 1 of 5",
    ).closest("[aria-live]");
    expect(liveRegion).toHaveAttribute("aria-live", "polite");
  });

  it("shows phase label from getPhaseLabel", () => {
    render(
      <ProcessingModal
        open={true}
        phase="caption_generation"
        statusText="Working..."
      />,
    );
    expect(screen.getByText("Caption Generation")).toBeInTheDocument();
  });

  it("does not show close button or retry in normal mode", () => {
    render(
      <ProcessingModal
        open={true}
        phase="analysis"
        statusText="Analyzing..."
      />,
    );
    expect(
      screen.queryByRole("button", { name: /close/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /retry/i }),
    ).not.toBeInTheDocument();
  });

  it("does not show spinner in error state", () => {
    render(
      <ProcessingModal
        open={true}
        phase="analysis"
        error="Something went wrong"
        onRetry={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

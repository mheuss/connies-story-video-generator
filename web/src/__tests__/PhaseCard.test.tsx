import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PhaseCard } from "../components/PhaseCard";

describe("PhaseCard", () => {
  it("renders phase label and completed badge", () => {
    render(<PhaseCard phase="analysis" label="Analysis" status="completed" />);
    expect(screen.getByText("Analysis")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });

  it("renders pending state with lock indicator", () => {
    render(
      <PhaseCard
        phase="image_generation"
        label="Image Generation"
        status="pending"
      />,
    );
    expect(screen.getByText("Image Generation")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders checkpoint state with awaiting review badge", () => {
    render(
      <PhaseCard
        phase="tts_generation"
        label="TTS Generation"
        status="checkpoint"
      >
        <div>Review content</div>
      </PhaseCard>,
    );
    expect(screen.getByText("Awaiting review")).toBeInTheDocument();
    expect(screen.getByText("Review content")).toBeInTheDocument();
  });

  it("renders stale state with warning badge", () => {
    render(
      <PhaseCard
        phase="narration_flagging"
        label="Narration Flagging"
        status="stale"
      />,
    );
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });

  it("renders failed state with error and retry button", () => {
    const onRetry = vi.fn();
    render(
      <PhaseCard
        phase="image_generation"
        label="Image Generation"
        status="failed"
        error="API timeout"
        onRetry={onRetry}
      />,
    );
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("API timeout")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("completed phase is collapsed by default and expandable", async () => {
    const user = userEvent.setup();
    render(
      <PhaseCard phase="analysis" label="Analysis" status="completed">
        <div>Artifact content</div>
      </PhaseCard>,
    );
    expect(screen.queryByText("Artifact content")).not.toBeInTheDocument();
    await user.click(screen.getByText("Analysis"));
    expect(screen.getByText("Artifact content")).toBeInTheDocument();
  });

  it("checkpoint phase is always expanded", () => {
    render(
      <PhaseCard phase="analysis" label="Analysis" status="checkpoint">
        <div>Review content</div>
      </PhaseCard>,
    );
    expect(screen.getByText("Review content")).toBeInTheDocument();
  });

  it("failed phase is always expanded", () => {
    render(
      <PhaseCard
        phase="analysis"
        label="Analysis"
        status="failed"
        error="Something broke"
      >
        <div>Error details</div>
      </PhaseCard>,
    );
    expect(screen.getByText("Error details")).toBeInTheDocument();
    expect(screen.getByText("Something broke")).toBeInTheDocument();
  });

  it("calls onRetry when retry button is clicked", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(
      <PhaseCard
        phase="analysis"
        label="Analysis"
        status="failed"
        error="Network error"
        onRetry={onRetry}
      />,
    );
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("running phase shows running badge", () => {
    render(
      <PhaseCard phase="analysis" label="Analysis" status="running" />,
    );
    expect(screen.getByText("Running...")).toBeInTheDocument();
  });

  it("stale phase shows stale message", () => {
    render(
      <PhaseCard
        phase="analysis"
        label="Analysis"
        status="stale"
      />,
    );
    expect(
      screen.getByText(
        "Upstream phase was re-edited. Re-run to update.",
      ),
    ).toBeInTheDocument();
  });

  it("decorative status icons are hidden from assistive technology", () => {
    render(
      <PhaseCard phase="analysis" label="Analysis" status="completed" />,
    );
    const icon = screen.getByTestId("phase-status-icon");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("pending phase has no expandable body", () => {
    render(
      <PhaseCard phase="analysis" label="Analysis" status="pending">
        <div>Should not appear</div>
      </PhaseCard>,
    );
    expect(screen.queryByText("Should not appear")).not.toBeInTheDocument();
  });
});

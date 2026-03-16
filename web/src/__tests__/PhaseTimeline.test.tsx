import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PhaseTimeline } from "../components/PhaseTimeline";

describe("PhaseTimeline", () => {
  it("renders all phases for adapt mode", () => {
    render(
      <PhaseTimeline
        mode="adapt"
        currentPhase="scene_splitting"
        projectStatus="in_progress"
      />
    );
    expect(screen.getByText("Analysis")).toBeInTheDocument();
    expect(screen.getByText("Scene Splitting")).toBeInTheDocument();
    expect(screen.getByText("Video Assembly")).toBeInTheDocument();
  });

  it("renders all phases for original mode", () => {
    render(
      <PhaseTimeline
        mode="original"
        currentPhase="analysis"
        projectStatus="in_progress"
      />
    );
    expect(screen.getByText("Story Bible")).toBeInTheDocument();
    expect(screen.getByText("Outline")).toBeInTheDocument();
    expect(screen.getByText("Scene Prose")).toBeInTheDocument();
  });

  it("marks phases before current as completed", () => {
    render(
      <PhaseTimeline
        mode="adapt"
        currentPhase="narration_flagging"
        projectStatus="in_progress"
      />
    );
    const badges = screen.getAllByText("Completed");
    expect(badges.length).toBe(2); // analysis + scene_splitting
  });

  it("marks phases after current as pending", () => {
    render(
      <PhaseTimeline
        mode="adapt"
        currentPhase="analysis"
        projectStatus="in_progress"
      />
    );
    const badges = screen.getAllByText("Pending");
    expect(badges.length).toBe(8); // 9 phases - 1 running
  });

  it("renders all phases as pending when no current phase", () => {
    render(
      <PhaseTimeline
        mode="adapt"
        currentPhase={null}
        projectStatus="pending"
      />
    );
    const badges = screen.getAllByText("Pending");
    expect(badges.length).toBe(9);
  });

  it("applies stale override to downstream phases", () => {
    render(
      <PhaseTimeline
        mode="adapt"
        currentPhase="video_assembly"
        projectStatus="completed"
        staleAfter="scene_splitting"
      />
    );
    // narration_flagging through caption_generation should be stale (6 phases)
    // video_assembly is current (completed), analysis and scene_splitting are completed
    const staleBadges = screen.getAllByText("Stale");
    expect(staleBadges.length).toBe(6);
  });

  it("uses semantic ordered list for timeline", () => {
    const { container } = render(
      <PhaseTimeline
        mode="adapt"
        currentPhase={null}
        projectStatus="pending"
      />
    );
    expect(container.querySelector("ol")).toBeInTheDocument();
  });
});

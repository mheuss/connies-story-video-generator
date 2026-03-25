import { describe, it, expect } from "vitest";
import {
  getPhaseSequence,
  getPhaseLabel,
  derivePhaseStatuses,
} from "../data/phases";

describe("getPhaseSequence", () => {
  it("returns 9 phases for adapt mode", () => {
    const phases = getPhaseSequence("adapt");
    expect(phases).toHaveLength(9);
    expect(phases[0]).toBe("analysis");
    expect(phases[phases.length - 1]).toBe("video_assembly");
  });

  it("returns 11 phases for original mode", () => {
    const phases = getPhaseSequence("original");
    expect(phases).toHaveLength(11);
    expect(phases).toContain("story_bible");
    expect(phases).toContain("outline");
  });

  it("returns 11 phases for inspired_by mode", () => {
    const phases = getPhaseSequence("inspired_by");
    expect(phases).toHaveLength(11);
  });
});

describe("getPhaseLabel", () => {
  it("converts snake_case to human-readable labels", () => {
    expect(getPhaseLabel("scene_splitting")).toBe("Scene Splitting");
    expect(getPhaseLabel("tts_generation")).toBe("TTS Generation");
    expect(getPhaseLabel("video_assembly")).toBe("Video Assembly");
  });
});

describe("derivePhaseStatuses", () => {
  it("marks phases before current as completed", () => {
    const statuses = derivePhaseStatuses("adapt", "narration_flagging", "in_progress");
    expect(statuses["analysis"]).toBe("completed");
    expect(statuses["scene_splitting"]).toBe("completed");
    expect(statuses["narration_flagging"]).toBe("running");
  });

  it("marks phases after current as pending", () => {
    const statuses = derivePhaseStatuses("adapt", "analysis", "in_progress");
    expect(statuses["scene_splitting"]).toBe("pending");
    expect(statuses["video_assembly"]).toBe("pending");
  });

  it("marks all phases as pending when no current phase", () => {
    const statuses = derivePhaseStatuses("adapt", null, "pending");
    const phases = getPhaseSequence("adapt");
    for (const phase of phases) {
      expect(statuses[phase]).toBe("pending");
    }
  });

  it("maps awaiting_review to checkpoint", () => {
    const statuses = derivePhaseStatuses("adapt", "image_prompts", "awaiting_review");
    expect(statuses["image_prompts"]).toBe("checkpoint");
  });

  it("maps failed status to failed", () => {
    const statuses = derivePhaseStatuses("adapt", "tts_generation", "failed");
    expect(statuses["tts_generation"]).toBe("failed");
  });
});

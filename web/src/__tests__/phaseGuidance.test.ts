import { describe, it, expect } from "vitest";
import { getPhaseGuidance } from "../data/phaseGuidance";

describe("getPhaseGuidance", () => {
  it("returns guidance for known checkpoint phases", () => {
    const g = getPhaseGuidance("analysis");
    expect(g).toBeTruthy();
    expect(g!.title).toBeTruthy();
    expect(g!.description).toBeTruthy();
  });

  it("returns guidance for all checkpoint phases", () => {
    const phases = [
      "analysis",
      "story_bible",
      "outline",
      "scene_prose",
      "critique_revision",
      "scene_splitting",
      "narration_flagging",
      "image_prompts",
      "narration_prep",
      "tts_generation",
    ];
    for (const phase of phases) {
      expect(getPhaseGuidance(phase)).toBeTruthy();
    }
  });

  it("returns null for non-checkpoint phases", () => {
    expect(getPhaseGuidance("video_assembly")).toBeNull();
    expect(getPhaseGuidance("nonexistent")).toBeNull();
  });
});

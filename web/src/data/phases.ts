export type PhaseStatus =
  | "completed"
  | "running"
  | "checkpoint"
  | "stale"
  | "pending"
  | "failed";

const ADAPT_PHASES = [
  "analysis",
  "scene_splitting",
  "narration_flagging",
  "image_prompts",
  "narration_prep",
  "tts_generation",
  "image_generation",
  "caption_generation",
  "video_assembly",
] as const;

const CREATIVE_PHASES = [
  "analysis",
  "story_bible",
  "outline",
  "scene_prose",
  "critique_revision",
  "image_prompts",
  "narration_prep",
  "tts_generation",
  "image_generation",
  "caption_generation",
  "video_assembly",
] as const;

export type PhaseName = (typeof ADAPT_PHASES)[number] | (typeof CREATIVE_PHASES)[number];

export function getPhaseSequence(mode: string): readonly string[] {
  if (mode === "adapt") return ADAPT_PHASES;
  return CREATIVE_PHASES;
}

const PHASE_LABELS: Record<string, string> = {
  analysis: "Analysis",
  story_bible: "Story Bible",
  outline: "Outline",
  scene_prose: "Scene Prose",
  critique_revision: "Critique & Revision",
  scene_splitting: "Scene Splitting",
  narration_flagging: "Narration Flagging",
  image_prompts: "Image Prompts",
  narration_prep: "Narration Prep",
  tts_generation: "TTS Generation",
  image_generation: "Image Generation",
  caption_generation: "Caption Generation",
  video_assembly: "Video Assembly",
};

export function getPhaseLabel(phase: string): string {
  return PHASE_LABELS[phase] ?? phase.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Derive per-phase statuses from project state.
 *
 * All phases before current_phase are completed.
 * current_phase maps from the overall project status.
 * All phases after current_phase are pending.
 */
export function derivePhaseStatuses(
  mode: string,
  currentPhase: string | null,
  projectStatus: string,
): Record<string, PhaseStatus> {
  const phases = getPhaseSequence(mode);
  const statuses: Record<string, PhaseStatus> = {};

  if (!currentPhase) {
    const fallback: PhaseStatus =
      projectStatus === "completed" ? "completed" : "pending";
    for (const phase of phases) {
      statuses[phase] = fallback;
    }
    return statuses;
  }

  const currentIdx = phases.indexOf(currentPhase);

  for (let i = 0; i < phases.length; i++) {
    if (currentIdx < 0) {
      statuses[phases[i]] = "pending";
    } else if (i < currentIdx) {
      statuses[phases[i]] = "completed";
    } else if (i === currentIdx) {
      statuses[phases[i]] = mapProjectStatus(projectStatus);
    } else {
      statuses[phases[i]] = "pending";
    }
  }

  return statuses;
}

function mapProjectStatus(status: string): PhaseStatus {
  switch (status) {
    case "in_progress":
      return "running";
    case "completed":
      return "completed";
    case "awaiting_review":
      return "checkpoint";
    case "failed":
      return "failed";
    default:
      return "pending";
  }
}

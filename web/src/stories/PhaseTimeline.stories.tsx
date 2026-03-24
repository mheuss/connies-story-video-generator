import type { Meta, StoryObj } from "@storybook/react-vite";
import { PhaseTimeline } from "../components/PhaseTimeline";

const meta: Meta<typeof PhaseTimeline> = {
  title: "Components/PhaseTimeline",
  component: PhaseTimeline,
  args: {
    mode: "adapt",
  },
};
export default meta;

type Story = StoryObj<typeof PhaseTimeline>;

export const AllPending: Story = {
  args: {
    currentPhase: null,
    projectStatus: "idle",
  },
};

export const EarlyPhaseRunning: Story = {
  args: {
    currentPhase: "scene_splitting",
    projectStatus: "in_progress",
  },
};

export const MidwayCheckpoint: Story = {
  args: {
    currentPhase: "tts_generation",
    projectStatus: "awaiting_review",
  },
};

export const PhaseFailed: Story = {
  args: {
    currentPhase: "image_generation",
    projectStatus: "failed",
    phaseErrors: { image_generation: "API rate limit exceeded" },
    onRetry: (phase: string) => console.log(`retry ${phase}`),
  },
};

export const AllCompleted: Story = {
  args: {
    currentPhase: "video_assembly",
    projectStatus: "completed",
  },
};

export const WithStalePhases: Story = {
  args: {
    currentPhase: "video_assembly",
    projectStatus: "completed",
    staleAfter: "scene_splitting",
  },
};

export const CreativeMode: Story = {
  args: {
    mode: "creative",
    currentPhase: "critique_revision",
    projectStatus: "in_progress",
  },
};

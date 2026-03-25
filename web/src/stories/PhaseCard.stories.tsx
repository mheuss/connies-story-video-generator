import type { Meta, StoryObj } from "@storybook/react-vite";
import { PhaseCard } from "../components/PhaseCard";

const meta: Meta<typeof PhaseCard> = {
  title: "Components/PhaseCard",
  component: PhaseCard,
  args: {
    phase: "analysis",
    label: "Analysis",
  },
};
export default meta;

type Story = StoryObj<typeof PhaseCard>;

export const Pending: Story = {
  args: { status: "pending" },
};

export const Running: Story = {
  args: {
    status: "running",
    children: <p className="text-sm text-muted-foreground">Analyzing source material...</p>,
  },
};

export const Completed: Story = {
  args: {
    status: "completed",
    children: <p className="text-sm text-muted-foreground">3 scenes identified, 2 characters extracted.</p>,
  },
};

export const Checkpoint: Story = {
  args: {
    status: "checkpoint",
    phase: "tts_generation",
    label: "TTS Generation",
    children: <p className="text-sm text-muted-foreground">Review the generated audio before continuing.</p>,
  },
};

export const Stale: Story = {
  args: {
    status: "stale",
    phase: "image_prompts",
    label: "Image Prompts",
    children: <p className="text-sm text-muted-foreground">3 prompts generated from scene descriptions.</p>,
  },
};

export const Failed: Story = {
  args: {
    status: "failed",
    phase: "tts_generation",
    label: "TTS Generation",
    error: "OpenAI API rate limit exceeded. Please try again in a few minutes.",
    onRetry: () => console.log("retry clicked"),
    children: null,
  },
};

export const FailedWithoutRetry: Story = {
  args: {
    status: "failed",
    phase: "video_assembly",
    label: "Video Assembly",
    error: "FFmpeg not found. Install FFmpeg to assemble the video.",
  },
};
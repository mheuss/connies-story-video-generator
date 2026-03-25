import type { Meta, StoryObj } from "@storybook/react-vite";
import { ProcessingModal } from "../components/ProcessingModal";

const meta: Meta<typeof ProcessingModal> = {
  title: "Components/ProcessingModal",
  component: ProcessingModal,
  args: {
    open: true,
    phase: "analysis",
  },
};
export default meta;

type Story = StoryObj<typeof ProcessingModal>;

export const Loading: Story = {
  args: {
    statusText: "Analyzing source material...",
  },
};

export const LoadingLaterPhase: Story = {
  args: {
    phase: "tts_generation",
    statusText: "Processing scene 3 of 5...",
  },
};

export const Error: Story = {
  args: {
    phase: "image_generation",
    error: "OpenAI API rate limit exceeded. Please wait and try again.",
    onRetry: () => console.log("retry clicked"),
    onClose: () => console.log("close clicked"),
  },
};

export const Closed: Story = {
  args: {
    open: false,
  },
};

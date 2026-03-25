import type { Meta, StoryObj } from "@storybook/react-vite";
import { ArtifactViewer } from "../components/ArtifactViewer";

/**
 * ArtifactViewer loads artifacts from the backend API on mount.
 * These stories require a running backend (`python -m story_video web`)
 * with real project data. Without a backend, they show the loading → error
 * transition, which is still useful for verifying those UI states.
 */
const meta: Meta<typeof ArtifactViewer> = {
  title: "Components/ArtifactViewer",
  component: ArtifactViewer,
  args: {
    projectId: "example-project-id",
    phase: "analysis",
  },
};
export default meta;

type Story = StoryObj<typeof ArtifactViewer>;

export const ReadOnly: Story = {
  args: {
    editable: false,
  },
};

export const Editable: Story = {
  args: {
    editable: true,
  },
};

export const DifferentPhase: Story = {
  args: {
    phase: "image_prompts",
    editable: true,
  },
};

import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";
import ReviewScreen from "../components/ReviewScreen";

const meta: Meta<typeof ReviewScreen> = {
  title: "Components/ReviewScreen",
  component: ReviewScreen,
  decorators: [(Story) => <MemoryRouter><Story /></MemoryRouter>],
};
export default meta;

type Story = StoryObj<typeof ReviewScreen>;

export const WithArtifacts: Story = {
  args: {
    projectId: "adapt-2026-02-25",
    checkpoint: { phase: "analysis", project_id: "adapt-2026-02-25" },
  },
};

export const EmptyArtifacts: Story = {
  args: {
    projectId: "adapt-2026-02-25",
    checkpoint: { phase: "outline", project_id: "adapt-2026-02-25" },
  },
};

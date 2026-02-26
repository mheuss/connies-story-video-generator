import type { Meta, StoryObj } from "@storybook/react";
import ApiKeySetup from "../components/ApiKeySetup";

const meta: Meta<typeof ApiKeySetup> = {
  title: "Components/ApiKeySetup",
  component: ApiKeySetup,
  parameters: { layout: "centered" },
};
export default meta;

type Story = StoryObj<typeof ApiKeySetup>;

export const Default: Story = {
  args: { onComplete: () => console.log("Keys saved") },
};

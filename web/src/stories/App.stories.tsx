import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";

const meta: Meta<typeof App> = {
  title: "App",
  component: App,
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Story />
      </MemoryRouter>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof App>;

export const Default: Story = {};

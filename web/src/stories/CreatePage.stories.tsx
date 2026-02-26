import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";
import CreatePage from "../pages/CreatePage";

const meta: Meta<typeof CreatePage> = {
  title: "Pages/CreatePage",
  component: CreatePage,
  decorators: [(Story) => <MemoryRouter><Story /></MemoryRouter>],
};
export default meta;

type Story = StoryObj<typeof CreatePage>;

export const Default: Story = {};

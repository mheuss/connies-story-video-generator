import type { Meta, StoryObj } from "@storybook/react-vite";
import { MemoryRouter } from "react-router-dom";
import SettingsPage from "../pages/SettingsPage";

const meta: Meta<typeof SettingsPage> = {
  title: "Pages/SettingsPage",
  component: SettingsPage,
  decorators: [(Story) => <MemoryRouter><Story /></MemoryRouter>],
};
export default meta;

type Story = StoryObj<typeof SettingsPage>;

export const Default: Story = {};

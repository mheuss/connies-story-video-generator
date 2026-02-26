import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ProjectPage from "../pages/ProjectPage";

const meta: Meta<typeof ProjectPage> = {
  title: "Pages/ProjectPage",
  component: ProjectPage,
  // Skip automated Storybook tests — ProjectPage opens an SSE connection via
  // useProgressStream that fails without a running backend or MSW mock.
  tags: ["!test"],
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/project/test-project"]}>
        <Routes>
          <Route path="/project/:projectId" element={<Story />} />
        </Routes>
      </MemoryRouter>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof ProjectPage>;

export const Processing: Story = {};

import type { Meta, StoryObj } from "@storybook/react";
import ProgressBar from "../components/ProgressBar";

const meta: Meta<typeof ProgressBar> = {
  title: "Components/ProgressBar",
  component: ProgressBar,
};
export default meta;

type Story = StoryObj<typeof ProgressBar>;

export const Indeterminate: Story = { args: { phase: "analysis", scenesDone: 0, scenesTotal: 0 } };
export const ZeroProgress: Story = { args: { phase: "tts_generation", scenesDone: 0, scenesTotal: 12 } };
export const EarlyProgress: Story = { args: { phase: "tts_generation", scenesDone: 2, scenesTotal: 12 } };
export const HalfDone: Story = { args: { phase: "image_generation", scenesDone: 6, scenesTotal: 12 } };
export const NearComplete: Story = { args: { phase: "caption_generation", scenesDone: 11, scenesTotal: 12 } };
export const Complete: Story = { args: { phase: "video_assembly", scenesDone: 12, scenesTotal: 12 } };

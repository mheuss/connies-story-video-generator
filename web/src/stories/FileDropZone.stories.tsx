import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { FileDropZone } from "../components/ui/FileDropZone";

const meta: Meta<typeof FileDropZone> = {
  title: "Components/FileDropZone",
  component: FileDropZone,
  args: {
    accept: [".txt", ".md"],
    maxSizeBytes: 10 * 1024 * 1024,
  },
};
export default meta;

type Story = StoryObj<typeof FileDropZone>;

export const Empty: Story = {
  args: {
    onFileRead: () => {},
    onClear: () => {},
  },
};

export const FileLoaded: Story = {
  args: {
    filename: "my_story.txt",
    onFileRead: () => {},
    onClear: () => {},
  },
};

export const WithError: Story = {
  args: {
    error: "Only .txt and .md files are supported",
    onFileRead: () => {},
    onClear: () => {},
  },
};

export const Disabled: Story = {
  args: {
    disabled: true,
    onFileRead: () => {},
    onClear: () => {},
  },
};

export const Interactive: Story = {
  render: (args) => {
    const [filename, setFilename] = useState<string | undefined>();
    return (
      <div className="max-w-md">
        <FileDropZone
          {...args}
          filename={filename}
          onFileRead={(_content, name) => setFilename(name)}
          onClear={() => setFilename(undefined)}
        />
      </div>
    );
  },
  args: {
    onFileRead: () => {},
    onClear: () => {},
  },
};

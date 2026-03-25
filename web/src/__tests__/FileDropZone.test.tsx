import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FileDropZone } from "../components/ui/FileDropZone";

function createFile(name: string, content: string, type = "text/plain"): File {
  return new File([content], name, { type });
}

describe("FileDropZone", () => {
  const defaultProps = {
    accept: [".txt", ".md"],
    maxSizeBytes: 10 * 1024 * 1024,
    onFileRead: vi.fn(),
    onClear: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders drop zone with browse button", () => {
    render(<FileDropZone {...defaultProps} />);
    expect(screen.getByText(/drop a text file here/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /browse files/i }),
    ).toBeInTheDocument();
  });

  it("calls onFileRead with content and filename after file selection", async () => {
    render(<FileDropZone {...defaultProps} />);
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = createFile("story.txt", "Once upon a time");
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(defaultProps.onFileRead).toHaveBeenCalledWith(
        "Once upon a time",
        "story.txt",
      );
    });
  });

  it("accepts .md files", async () => {
    render(<FileDropZone {...defaultProps} />);
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = createFile("story.md", "# My Story");
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(defaultProps.onFileRead).toHaveBeenCalledWith(
        "# My Story",
        "story.md",
      );
    });
  });

  it("shows filename and remove button when filename prop is set", () => {
    render(<FileDropZone {...defaultProps} filename="story.txt" />);
    expect(screen.getByText("story.txt")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /remove/i }),
    ).toBeInTheDocument();
  });

  it("calls onClear when remove button is clicked", async () => {
    render(<FileDropZone {...defaultProps} filename="story.txt" />);
    await userEvent.click(screen.getByRole("button", { name: /remove/i }));
    expect(defaultProps.onClear).toHaveBeenCalled();
  });

  it("shows error for wrong file extension", async () => {
    render(<FileDropZone {...defaultProps} />);
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = createFile("story.pdf", "content", "application/pdf");
    // Use fireEvent.change to bypass the input's accept attribute filtering.
    // This simulates a file reaching the change handler (e.g., via drag-and-drop
    // which doesn't respect accept). userEvent.upload filters non-matching files.
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(
        screen.getByText(/only .txt and .md files are supported/i),
      ).toBeInTheDocument();
    });
    expect(defaultProps.onFileRead).not.toHaveBeenCalled();
  });

  it("shows error for file exceeding size limit", async () => {
    const props = { ...defaultProps, maxSizeBytes: 10 };
    render(<FileDropZone {...props} />);
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = createFile("story.txt", "This content exceeds 10 bytes");
    await userEvent.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText(/file too large/i)).toBeInTheDocument();
    });
    expect(defaultProps.onFileRead).not.toHaveBeenCalled();
  });

  it("shows drag-over visual feedback", () => {
    render(<FileDropZone {...defaultProps} />);
    const dropZone = screen
      .getByText(/drop a text file here/i)
      .closest("div")!;
    fireEvent.dragEnter(dropZone, { dataTransfer: { types: ["Files"] } });
    expect(dropZone).toHaveClass("border-blue-500");
  });

  it("calls onFileRead when a file is dropped", async () => {
    render(<FileDropZone {...defaultProps} />);
    const dropZone = screen.getByText(/drop a text file here/i).closest("div")!;
    const file = createFile("story.txt", "Dropped content");
    const dataTransfer = { files: [file], types: ["Files"] };
    fireEvent.drop(dropZone, { dataTransfer });

    await waitFor(() => {
      expect(defaultProps.onFileRead).toHaveBeenCalledWith(
        "Dropped content",
        "story.txt",
      );
    });
  });

  it("hides drop zone when filename is set", () => {
    render(<FileDropZone {...defaultProps} filename="story.txt" />);
    expect(
      screen.queryByText(/drop a text file here/i),
    ).not.toBeInTheDocument();
  });

  it("shows external error message", () => {
    render(<FileDropZone {...defaultProps} error="Something went wrong" />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("disables interaction when disabled prop is true", () => {
    render(<FileDropZone {...defaultProps} disabled />);
    expect(
      screen.getByRole("button", { name: /browse files/i }),
    ).toBeDisabled();
  });

  it("marks error messages with role alert in drop zone state", () => {
    render(<FileDropZone {...defaultProps} error="Something went wrong" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
  });

  it("marks error messages with role alert in filename state", () => {
    render(
      <FileDropZone
        {...defaultProps}
        filename="story.txt"
        error="Upload failed"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Upload failed");
  });

  it("renders data-slot on root element in drop zone state", () => {
    const { container } = render(<FileDropZone {...defaultProps} />);
    expect(container.querySelector("[data-slot='file-drop-zone']")).toBeInTheDocument();
  });

  it("renders data-slot on root element in filename state", () => {
    const { container } = render(
      <FileDropZone {...defaultProps} filename="story.txt" />,
    );
    expect(container.querySelector("[data-slot='file-drop-zone']")).toBeInTheDocument();
  });

  it("derives hint text size from maxSizeBytes prop", () => {
    const props = { ...defaultProps, maxSizeBytes: 5 * 1024 * 1024 };
    render(<FileDropZone {...props} />);
    expect(screen.getByText(/up to 5 MB/)).toBeInTheDocument();
  });
});

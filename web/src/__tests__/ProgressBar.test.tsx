import { render, screen } from "@testing-library/react";
import ProgressBar from "../components/ProgressBar";

describe("ProgressBar", () => {
  it("renders phase name", () => {
    render(<ProgressBar phase="image_generation" scenesDone={3} scenesTotal={10} />);
    expect(screen.getByText(/image generation/i)).toBeInTheDocument();
  });

  it("shows scene count", () => {
    render(<ProgressBar phase="tts_generation" scenesDone={5} scenesTotal={10} />);
    expect(screen.getByText("5 / 10")).toBeInTheDocument();
  });

  it("renders a progress element", () => {
    render(<ProgressBar phase="analysis" scenesDone={2} scenesTotal={8} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "2");
    expect(bar).toHaveAttribute("aria-valuemax", "8");
  });

  it("shows indeterminate mode when scenesTotal is 0", () => {
    render(<ProgressBar phase="analysis" scenesDone={0} scenesTotal={0} />);
    expect(screen.getByText("Working...")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar");
    expect(bar).not.toHaveAttribute("aria-valuenow");
    expect(bar).not.toHaveAttribute("aria-valuemax");
  });
});

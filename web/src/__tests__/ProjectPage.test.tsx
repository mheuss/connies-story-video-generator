import { render, screen, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi, beforeEach, afterEach } from "vitest";
import ProjectPage from "../pages/ProjectPage";

// Reuse MockEventSource
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {};
  onerror: ((event: Event) => void) | null = null;
  readyState = 1;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(listener);
  }
  removeEventListener() {}
  close() {
    this.readyState = 2;
  }
  emit(type: string, data: string) {
    const event = new MessageEvent(type, { data });
    (this.listeners[type] || []).forEach((l) => l(event));
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderProjectPage(projectId: string) {
  return render(
    <MemoryRouter initialEntries={[`/project/${projectId}`]}>
      <Routes>
        <Route path="/project/:projectId" element={<ProjectPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProjectPage", () => {
  it("shows processing state initially", () => {
    renderProjectPage("test-project");
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Starting pipeline...")).toBeInTheDocument();
  });

  it("shows current phase when phase_started arrives", () => {
    renderProjectPage("test-project");
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("phase_started", JSON.stringify({ phase: "analysis", scene_count: 5 }));
    });

    expect(screen.getByText("Current phase:")).toBeInTheDocument();
    // Phase name appears in both the status line and the progress bar
    expect(screen.getAllByText("analysis").length).toBeGreaterThanOrEqual(1);
  });

  it("shows indeterminate progress bar on phase start, then determinate after scene_progress", () => {
    renderProjectPage("test-project");
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("phase_started", JSON.stringify({ phase: "image_generation", scene_count: 10 }));
    });

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText("Working...")).toBeInTheDocument();

    act(() => {
      es.emit("scene_progress", JSON.stringify({ phase: "image_generation", scene_number: 3, total: 10 }));
    });

    expect(screen.getByText("3 / 10")).toBeInTheDocument();
  });

  it("shows video when completed", () => {
    renderProjectPage("test-project");
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("completed", JSON.stringify({}));
    });

    expect(screen.getByText("Video Complete")).toBeInTheDocument();
  });

  it("shows error on error event", () => {
    renderProjectPage("test-project");
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("error", JSON.stringify({ message: "TTS failed" }));
    });

    expect(screen.getByText("TTS failed")).toBeInTheDocument();
  });

  it("shows retry button on error", () => {
    renderProjectPage("test-project");
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("error", JSON.stringify({ message: "TTS failed" }));
    });

    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("shows download link when video is complete", () => {
    renderProjectPage("test-project");
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("completed", JSON.stringify({}));
    });

    expect(screen.getByRole("link", { name: /download/i })).toBeInTheDocument();
  });
});

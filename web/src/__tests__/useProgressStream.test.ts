import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useProgressStream } from "../hooks/useProgressStream";

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {};
  onerror: ((event: Event) => void) | null = null;
  readyState = 0;

  constructor(url: string) {
    this.url = url;
    this.readyState = 1; // OPEN
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(listener);
  }

  removeEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (this.listeners[type]) {
      this.listeners[type] = this.listeners[type].filter((l) => l !== listener);
    }
  }

  close() {
    this.readyState = 2; // CLOSED
  }

  // Test helper: simulate an event
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

describe("useProgressStream", () => {
  it("connects to the SSE endpoint", () => {
    renderHook(() => useProgressStream("test-project"));
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe("/api/v1/projects/test-project/progress");
  });

  it("receives phase_started events", () => {
    const { result } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("phase_started", JSON.stringify({ phase: "analysis", scene_count: 5 }));
    });

    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0].event).toBe("phase_started");
    expect(result.current.currentPhase).toBe("analysis");
  });

  it("sets isComplete on completed event", () => {
    const { result } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("completed", JSON.stringify({}));
    });

    expect(result.current.isComplete).toBe(true);
  });

  it("sets checkpoint on checkpoint event", () => {
    const { result } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("checkpoint", JSON.stringify({ phase: "analysis", project_id: "test-project" }));
    });

    expect(result.current.checkpoint).toEqual({ phase: "analysis", project_id: "test-project" });
  });

  it("closes connection on unmount", () => {
    const { unmount } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    unmount();
    expect(es.readyState).toBe(2); // CLOSED
  });
});

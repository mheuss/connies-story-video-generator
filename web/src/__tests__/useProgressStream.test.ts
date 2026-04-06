import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useProgressStream } from "../hooks/useProgressStream";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: {
    getProject: vi.fn(),
  },
}));

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
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
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

  it("tracks scene progress from scene_progress events", () => {
    const { result } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("phase_started", JSON.stringify({ phase: "image_generation", scene_count: 10 }));
    });

    expect(result.current.scenesDone).toBe(0);
    expect(result.current.scenesTotal).toBe(0);

    act(() => {
      es.emit("scene_progress", JSON.stringify({ phase: "image_generation", scene_number: 3, total: 10 }));
    });

    expect(result.current.scenesDone).toBe(3);
    expect(result.current.scenesTotal).toBe(10);
  });

  it("resets scenesDone when a new phase starts", () => {
    const { result } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("phase_started", JSON.stringify({ phase: "tts_generation", scene_count: 8 }));
      es.emit("scene_progress", JSON.stringify({ phase: "tts_generation", scene_number: 5, total: 8 }));
    });

    expect(result.current.scenesDone).toBe(5);

    act(() => {
      es.emit("phase_started", JSON.stringify({ phase: "image_generation", scene_count: 8 }));
    });

    expect(result.current.scenesDone).toBe(0);
    expect(result.current.scenesTotal).toBe(0);
  });

  it("closes connection on unmount", () => {
    const { unmount } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    unmount();
    expect(es.readyState).toBe(2); // CLOSED
  });

  it("removes all event listeners on unmount", () => {
    const removeSpy = vi.spyOn(MockEventSource.prototype, "removeEventListener");
    const { unmount } = renderHook(() => useProgressStream("test-project"));
    const es = MockEventSource.instances[0];

    // Verify listeners were registered
    const registeredTypes = Object.keys(es.listeners);
    expect(registeredTypes).toContain("phase_started");
    expect(registeredTypes).toContain("completed");

    unmount();

    // Verify removeEventListener was called for each registered event type
    const removedTypes = removeSpy.mock.calls.map((call) => call[0]);
    for (const type of ["phase_started", "scene_progress", "checkpoint", "completed", "error"]) {
      expect(removedTypes).toContain(type);
    }

    removeSpy.mockRestore();
  });

  describe("conditional connection", () => {
    it("does not connect SSE when enabled is false", () => {
      renderHook(() => useProgressStream("test-project", { enabled: false }));
      expect(MockEventSource.instances).toHaveLength(0);
    });

    it("connects SSE when enabled is true", () => {
      renderHook(() => useProgressStream("test-project", { enabled: true }));
      expect(MockEventSource.instances).toHaveLength(1);
    });

    it("connects when enabled transitions from false to true", () => {
      const { rerender } = renderHook(
        ({ enabled }) => useProgressStream("test-project", { enabled }),
        { initialProps: { enabled: false } }
      );
      expect(MockEventSource.instances).toHaveLength(0);

      rerender({ enabled: true });
      expect(MockEventSource.instances).toHaveLength(1);
    });
  });

  describe("reconnection", () => {
    it("detects completed state via REST on reconnect", async () => {
      vi.mocked(api.getProject).mockResolvedValue({
        project_id: "test-project",
        mode: "adapt",
        status: "completed",
        current_phase: null,
        scene_count: 2,
        created_at: "2026-01-01",
      });

      const { result } = renderHook(() => useProgressStream("test-project"));
      const es = MockEventSource.instances[0];

      // Trigger SSE error to start reconnect
      act(() => {
        es.onerror?.(new Event("error"));
      });

      // Advance past the reconnect delay (1s for first retry)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });

      expect(api.getProject).toHaveBeenCalledWith("test-project");
      expect(result.current.isComplete).toBe(true);
      // Should not have opened a second EventSource
      expect(MockEventSource.instances).toHaveLength(1);
    });

    it("detects awaiting_review state via REST on reconnect", async () => {
      vi.mocked(api.getProject).mockResolvedValue({
        project_id: "test-project",
        mode: "adapt",
        status: "awaiting_review",
        current_phase: "analysis",
        scene_count: 2,
        created_at: "2026-01-01",
      });

      const { result } = renderHook(() => useProgressStream("test-project"));
      const es = MockEventSource.instances[0];

      act(() => {
        es.onerror?.(new Event("error"));
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });

      expect(result.current.checkpoint).toEqual({
        phase: "analysis",
        project_id: "test-project",
      });
      expect(MockEventSource.instances).toHaveLength(1);
    });

    it("detects failed state via REST on reconnect", async () => {
      vi.mocked(api.getProject).mockResolvedValue({
        project_id: "test-project",
        mode: "adapt",
        status: "failed",
        current_phase: null,
        scene_count: 2,
        created_at: "2026-01-01",
      });

      const { result } = renderHook(() => useProgressStream("test-project"));
      const es = MockEventSource.instances[0];

      act(() => {
        es.onerror?.(new Event("error"));
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });

      expect(result.current.error).toBe("Pipeline failed");
      expect(MockEventSource.instances).toHaveLength(1);
    });

    it("falls back to SSE reconnect when REST check fails", async () => {
      vi.mocked(api.getProject).mockRejectedValue(new Error("Network error"));

      renderHook(() => useProgressStream("test-project"));
      const es = MockEventSource.instances[0];

      act(() => {
        es.onerror?.(new Event("error"));
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500);
      });

      // Should have opened a second EventSource after REST failure
      expect(MockEventSource.instances).toHaveLength(2);
    });

    it("does not double-connect on rapid consecutive errors", async () => {
      vi.mocked(api.getProject).mockResolvedValue({
        project_id: "test-project",
        mode: "adapt",
        status: "in_progress",
        current_phase: "analysis",
        scene_count: 2,
        created_at: "2026-01-01",
      });

      renderHook(() => useProgressStream("test-project"));
      const es = MockEventSource.instances[0];

      // Fire two errors rapidly before any timeout resolves
      act(() => {
        es.onerror?.(new Event("error"));
        es.onerror?.(new Event("error"));
      });

      // Advance past both potential timeouts
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000);
      });

      // Should have only one reconnection (2 total: initial + 1 reconnect)
      expect(MockEventSource.instances).toHaveLength(2);
    });

    it("resets retry count after successful reconnection message", async () => {
      vi.mocked(api.getProject).mockResolvedValue({
        project_id: "test-project",
        mode: "adapt",
        status: "in_progress",
        current_phase: "analysis",
        scene_count: 2,
        created_at: "2026-01-01",
      });

      const { result } = renderHook(() => useProgressStream("test-project"));

      // Burn through 4 retries (leaving 1 remaining)
      for (let i = 0; i < 4; i++) {
        const es = MockEventSource.instances[MockEventSource.instances.length - 1];
        act(() => {
          es.onerror?.(new Event("error"));
        });
        await act(async () => {
          await vi.advanceTimersByTimeAsync((i + 1) * 1000 + 500);
        });
      }

      // Now get a successful message on the reconnected EventSource
      const reconnectedEs = MockEventSource.instances[MockEventSource.instances.length - 1];
      act(() => {
        reconnectedEs.emit("phase_started", JSON.stringify({ phase: "analysis" }));
      });

      // Retry count should be reset — 5 more errors should be tolerable
      for (let i = 0; i < 5; i++) {
        const es = MockEventSource.instances[MockEventSource.instances.length - 1];
        act(() => {
          es.onerror?.(new Event("error"));
        });
        await act(async () => {
          await vi.advanceTimersByTimeAsync((i + 1) * 1000 + 500);
        });
      }

      // Should NOT have hit the "Connection lost" error yet
      // (6th error exhausts retries)
      const lastEs = MockEventSource.instances[MockEventSource.instances.length - 1];
      act(() => {
        lastEs.onerror?.(new Event("error"));
      });

      expect(result.current.error).toBe("Connection lost after multiple retries");
    });

    it("shows error after exhausting all retries", async () => {
      vi.mocked(api.getProject).mockResolvedValue({
        project_id: "test-project",
        mode: "adapt",
        status: "in_progress",
        current_phase: "analysis",
        scene_count: 2,
        created_at: "2026-01-01",
      });

      const { result } = renderHook(() => useProgressStream("test-project"));

      // Burn through 5 retries
      for (let i = 0; i < 5; i++) {
        const es = MockEventSource.instances[MockEventSource.instances.length - 1];
        act(() => {
          es.onerror?.(new Event("error"));
        });
        await act(async () => {
          await vi.advanceTimersByTimeAsync((i + 1) * 1000 + 500);
        });
      }

      // 6th error should exhaust retries
      const lastEs = MockEventSource.instances[MockEventSource.instances.length - 1];
      act(() => {
        lastEs.onerror?.(new Event("error"));
      });

      expect(result.current.error).toBe("Connection lost after multiple retries");
    });
  });
});

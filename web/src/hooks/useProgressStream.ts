import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ProgressEvent } from "../api/types";

interface ProgressState {
  events: ProgressEvent[];
  currentPhase: string | null;
  checkpoint: { phase: string; project_id: string } | null;
  isComplete: boolean;
  error: string | null;
  scenesDone: number;
  scenesTotal: number;
}

interface UseProgressStreamResult extends ProgressState {
  reset: () => void;
}

const TERMINAL_EVENTS = new Set(["checkpoint", "completed", "error"]);
const SSE_EVENT_TYPES = ["phase_started", "scene_progress", "checkpoint", "completed", "error"];

const INITIAL_STATE: ProgressState = {
  events: [],
  currentPhase: null,
  checkpoint: null,
  isComplete: false,
  error: null,
  scenesDone: 0,
  scenesTotal: 0,
};

export function useProgressStream(projectId: string | null): UseProgressStreamResult {
  const [state, setState] = useState<ProgressState>(INITIAL_STATE);
  const esRef = useRef<EventSource | null>(null);
  const [resetCount, setResetCount] = useState(0);

  useEffect(() => {
    if (!projectId) return;

    let retryCount = 0;

    const connect = () => {
      const es = new EventSource(`/api/v1/projects/${projectId}/progress`);
      esRef.current = es;

      const handleEvent = (type: string) => (event: MessageEvent) => {
        const data = JSON.parse(event.data) as Record<string, unknown>;
        const progressEvent: ProgressEvent = { event: type as ProgressEvent["event"], data };

        // Successful message resets retry count
        retryCount = 0;

        setState((prev) => {
          const next = { ...prev, events: [...prev.events, progressEvent] };

          if (type === "phase_started") {
            next.currentPhase = (data.phase as string) || null;
            next.scenesDone = 0;
            next.scenesTotal = 0;
          } else if (type === "scene_progress") {
            next.scenesDone = (data.scene_number as number) || 0;
            next.scenesTotal = (data.total as number) || prev.scenesTotal;
          } else if (type === "checkpoint") {
            next.checkpoint = { phase: data.phase as string, project_id: data.project_id as string };
          } else if (type === "completed") {
            next.isComplete = true;
          } else if (type === "error") {
            next.error = (data.message as string) || "Pipeline failed";
          }

          return next;
        });

        if (TERMINAL_EVENTS.has(type)) {
          es.close();
        }
      };

      for (const type of SSE_EVENT_TYPES) {
        es.addEventListener(type, handleEvent(type));
      }

      es.onerror = () => {
        es.close();
        if (retryCount < 5) {
          retryCount++;
          setTimeout(async () => {
            // Check project status before reconnecting — the pipeline may
            // have reached a terminal state while we were disconnected.
            try {
              const status = await api.getProject(projectId);
              if (status.status === "completed") {
                setState((prev) => ({ ...prev, isComplete: true }));
                return;
              }
              if (status.status === "failed") {
                setState((prev) => ({ ...prev, error: "Pipeline failed" }));
                return;
              }
              if (status.status === "awaiting_review" && status.current_phase) {
                setState((prev) => ({
                  ...prev,
                  checkpoint: { phase: status.current_phase!, project_id: status.project_id },
                }));
                return;
              }
            } catch {
              // REST check failed too — fall through to SSE reconnect
            }
            connect();
          }, 1000 * retryCount);
        } else {
          setState((prev) => ({ ...prev, error: "Connection lost after multiple retries" }));
        }
      };
    };

    connect();

    return () => {
      esRef.current?.close();
    };
  }, [projectId, resetCount]);

  const reset = useCallback(() => {
    esRef.current?.close();
    setState(INITIAL_STATE);
    setResetCount((c) => c + 1);
  }, []);

  return { ...state, reset };
}

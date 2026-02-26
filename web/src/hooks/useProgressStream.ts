import { useEffect, useRef, useState } from "react";
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

const TERMINAL_EVENTS = new Set(["checkpoint", "completed", "error"]);
const SSE_EVENT_TYPES = ["phase_started", "scene_progress", "checkpoint", "completed", "error"];

export function useProgressStream(projectId: string | null): ProgressState {
  const [state, setState] = useState<ProgressState>({
    events: [],
    currentPhase: null,
    checkpoint: null,
    isComplete: false,
    error: null,
    scenesDone: 0,
    scenesTotal: 0,
  });
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!projectId) return;

    const es = new EventSource(`/api/v1/projects/${projectId}/progress`);
    esRef.current = es;

    const handleEvent = (type: string) => (event: MessageEvent) => {
      const data = JSON.parse(event.data) as Record<string, unknown>;
      const progressEvent: ProgressEvent = { event: type as ProgressEvent["event"], data };

      setState((prev) => {
        const next = { ...prev, events: [...prev.events, progressEvent] };

        if (type === "phase_started") {
          next.currentPhase = (data.phase as string) || null;
          next.scenesDone = 0;
          next.scenesTotal = (data.scene_count as number) || 0;
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
      setState((prev) => ({ ...prev, error: "Connection lost" }));
      es.close();
    };

    return () => {
      es.close();
    };
  }, [projectId]);

  return state;
}

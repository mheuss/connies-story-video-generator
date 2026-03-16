import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import type { ProjectStatus } from "@/api/types";
import { useProgressStream } from "@/hooks/useProgressStream";
import { PhaseTimeline } from "@/components/PhaseTimeline";
import { ProcessingModal } from "@/components/ProcessingModal";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export function UnifiedProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<ProjectStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [staleAfter, setStaleAfter] = useState<string | null>(null);

  const isRunning = project?.status === "in_progress";

  const progress = useProgressStream(projectId ?? "", { enabled: isRunning });

  // Fetch project status on mount
  useEffect(() => {
    if (!projectId || projectId === "new") return;
    setLoading(true);
    api
      .getProject(projectId)
      .then((data) => {
        setProject(data);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [projectId]);

  // Update project state from SSE events
  useEffect(() => {
    if (progress.isComplete && project) {
      setProject({ ...project, status: "completed" });
    }
    if (progress.checkpoint && project) {
      setProject({
        ...project,
        status: "awaiting_review",
        current_phase: progress.checkpoint.phase,
      });
    }
    if (progress.currentPhase && project && isRunning) {
      setProject({ ...project, current_phase: progress.currentPhase });
    }
    if (progress.error && project) {
      setProject({ ...project, status: "failed" });
    }
  }, [
    progress.isComplete,
    progress.checkpoint,
    progress.currentPhase,
    progress.error,
  ]);

  const handleStartPipeline = useCallback(async () => {
    if (!projectId) return;
    try {
      await api.startPipeline(projectId);
      setProject((prev) =>
        prev ? { ...prev, status: "in_progress" } : prev
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to start pipeline"
      );
    }
  }, [projectId]);

  const handleApprove = useCallback(
    async (auto?: boolean) => {
      if (!projectId) return;
      try {
        await api.approvePipeline(projectId, auto);
        setProject((prev) =>
          prev ? { ...prev, status: "in_progress" } : prev
        );
        setStaleAfter(null);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to approve");
      }
    },
    [projectId]
  );

  const handleRerunFrom = useCallback(
    async (phase: string) => {
      if (!projectId) return;
      try {
        await api.rerunFromPhase(projectId, phase);
        setProject((prev) =>
          prev ? { ...prev, status: "in_progress" } : prev
        );
        setStaleAfter(null);
        progress.reset();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to re-run");
      }
    },
    [projectId, progress]
  );

  // Build status text for processing modal
  const modalStatusText =
    progress.scenesTotal > 0
      ? `Processing scene ${progress.scenesDone + 1} of ${progress.scenesTotal}`
      : "Working...";

  // --- Render ---

  if (projectId === "new") {
    return <div>Creation form placeholder</div>;
  }

  if (loading) {
    return (
      <div className="p-8 text-center text-gray-500" role="status">
        Loading...
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="p-8 text-center">
        <p className="text-red-600 mb-4">{error}</p>
        <Button variant="outline" onClick={() => navigate("/")}>
          Back to projects
        </Button>
      </div>
    );
  }

  if (!project) return null;

  return (
    <div className="max-w-3xl mx-auto py-8 px-4">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-2">{project.project_id}</h1>
        <p className="text-sm text-gray-500">
          {project.mode} &middot; {project.scene_count} scenes
        </p>
      </div>

      {project.status === "completed" && (
        <Card className="mb-8">
          <CardHeader>
            <h2 className="text-lg font-semibold">Final Video</h2>
          </CardHeader>
          <CardContent>
            <video
              controls
              className="w-full rounded"
              src={`/api/v1/projects/${project.project_id}/artifacts/video_assembly/final.mp4`}
            />
            <a
              href={`/api/v1/projects/${project.project_id}/artifacts/video_assembly/final.mp4`}
              download
              className="inline-block mt-4 text-sm text-blue-600 hover:underline"
            >
              Download
            </a>
          </CardContent>
        </Card>
      )}

      {project.status === "pending" && (
        <div className="mb-8 text-center">
          <Button size="lg" onClick={handleStartPipeline}>
            Start Pipeline
          </Button>
        </div>
      )}

      <PhaseTimeline
        mode={project.mode}
        currentPhase={project.current_phase}
        projectStatus={project.status}
        staleAfter={staleAfter}
      />

      <ProcessingModal
        open={isRunning}
        phase={progress.currentPhase ?? project.current_phase ?? ""}
        statusText={modalStatusText}
        error={progress.error ?? undefined}
        onRetry={handleStartPipeline}
        onClose={() => setError(null)}
      />
    </div>
  );
}

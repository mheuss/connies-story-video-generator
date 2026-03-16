import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import type { CreateProjectRequest, ProjectStatus } from "@/api/types";
import { useProgressStream } from "@/hooks/useProgressStream";
import { getPhaseSequence } from "@/data/phases";
import ApiKeySetup from "@/components/ApiKeySetup";
import { ArtifactViewer } from "@/components/ArtifactViewer";
import { PhaseTimeline } from "@/components/PhaseTimeline";
import { ProcessingModal } from "@/components/ProcessingModal";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

type Mode = CreateProjectRequest["mode"];

const MODE_OPTIONS: { value: Mode; label: string; description: string }[] = [
  { value: "adapt", label: "Adapt", description: "Narrate an existing story" },
  { value: "original", label: "Original", description: "Write from a topic" },
  {
    value: "inspired_by",
    label: "Inspired By",
    description: "New story from existing",
  },
];

function CreationForm() {
  const navigate = useNavigate();
  const [keysReady, setKeysReady] = useState(false);
  const [mode, setMode] = useState<Mode>("adapt");
  const [sourceText, setSourceText] = useState("");
  const [autonomous, setAutonomous] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const handleKeysComplete = useCallback(() => setKeysReady(true), []);

  const sourceTextLabel =
    mode === "adapt" ? "Story to adapt" : "Topic or idea";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceText.trim()) return;

    setError(null);
    setCreating(true);

    try {
      const project = await api.createProject({
        mode,
        source_text: sourceText,
        autonomous,
      });
      navigate(`/project/${project.project_id}`, { replace: true });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create project"
      );
      setCreating(false);
    }
  };

  if (!keysReady) {
    return (
      <div className="max-w-xl mx-auto py-8 px-4">
        <ApiKeySetup onComplete={handleKeysComplete} />
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto py-8 px-4">
      <h1 className="text-2xl font-bold mb-6">Create a new story video</h1>

      <form onSubmit={handleSubmit} noValidate>
        {/* Mode selector */}
        <fieldset className="mb-6">
          <legend className="text-sm font-medium mb-2">
            Mode <span aria-hidden="true">*</span>
            <span className="sr-only">(required)</span>
          </legend>
          <div className="space-y-2">
            {MODE_OPTIONS.map((option) => (
              <label
                key={option.value}
                className="flex items-start gap-3 cursor-pointer rounded-lg border border-gray-200 p-3 has-[:checked]:border-blue-500 has-[:checked]:bg-blue-50 dark:border-gray-700 dark:has-[:checked]:border-blue-400 dark:has-[:checked]:bg-blue-950"
              >
                <input
                  type="radio"
                  name="mode"
                  value={option.value}
                  checked={mode === option.value}
                  onChange={() => setMode(option.value)}
                  className="mt-0.5 accent-blue-600 focus:ring-2 focus:ring-blue-500"
                />
                <div>
                  <span className="font-medium">{option.label}</span>
                  <span className="block text-sm text-gray-500">
                    {option.description}
                  </span>
                </div>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Source text */}
        <div className="mb-6">
          <label htmlFor="source-text" className="block text-sm font-medium mb-1">
            {sourceTextLabel} <span aria-hidden="true">*</span>
            <span className="sr-only">(required)</span>
          </label>
          <Textarea
            id="source-text"
            value={sourceText}
            onChange={(e) => setSourceText(e.target.value)}
            rows={8}
            required
            aria-required="true"
            placeholder={
              mode === "adapt"
                ? "Paste the full text of your story here..."
                : "Describe your story idea..."
            }
          />
        </div>

        {/* Autonomous toggle */}
        <div className="mb-6">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={autonomous}
              onChange={(e) => setAutonomous(e.target.checked)}
              className="rounded accent-blue-600 focus:ring-2 focus:ring-blue-500"
            />
            <span>
              Run to completion{" "}
              <span className="text-sm text-gray-500">
                (skip review checkpoints)
              </span>
            </span>
          </label>
        </div>

        {/* Error display */}
        {error && (
          <div role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Submit */}
        <Button
          type="submit"
          size="lg"
          disabled={creating || !sourceText.trim()}
        >
          {creating ? "Creating..." : "Create Project"}
        </Button>
      </form>
    </div>
  );
}

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

  // Track which phase was edited earliest
  const handleArtifactEdited = useCallback(
    (phase: string) => {
      setStaleAfter((prev) => {
        if (!prev) return phase;
        const phases = getPhaseSequence(project!.mode);
        return phases.indexOf(phase) < phases.indexOf(prev) ? phase : prev;
      });
    },
    [project]
  );

  // Render content inside each PhaseCard
  const renderPhaseContent = useCallback(
    (phase: string, status: string) => {
      if (status === "completed" || status === "checkpoint") {
        return (
          <>
            <ArtifactViewer
              projectId={project!.project_id}
              phase={phase}
              editable={status === "completed" || status === "checkpoint"}
              onEdited={handleArtifactEdited}
            />
            {staleAfter === phase && (
              <Button className="mt-4" onClick={() => handleRerunFrom(phase)}>
                Re-run from here
              </Button>
            )}
            {status === "checkpoint" && (
              <div className="flex gap-2 mt-4">
                <Button onClick={() => handleApprove()}>
                  Approve & Continue
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleApprove(true)}
                >
                  Auto-approve remaining
                </Button>
              </div>
            )}
          </>
        );
      }
      return null;
    },
    [project, staleAfter, handleArtifactEdited, handleRerunFrom, handleApprove]
  );

  // Build status text for processing modal
  const modalStatusText =
    progress.scenesTotal > 0
      ? `Processing scene ${progress.scenesDone + 1} of ${progress.scenesTotal}`
      : "Working...";

  // --- Render ---

  if (projectId === "new") {
    return <CreationForm />;
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
        renderPhaseContent={renderPhaseContent}
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

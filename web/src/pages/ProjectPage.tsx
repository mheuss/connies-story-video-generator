import { useParams } from "react-router-dom";
import { useProgressStream } from "../hooks/useProgressStream";
import ReviewScreen from "../components/ReviewScreen";
import ProgressBar from "../components/ProgressBar";
import { api } from "../api/client";

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const progress = useProgressStream(projectId ?? null);

  if (progress.error) {
    return (
      <div>
        <h2>Error</h2>
        <p style={{ color: "red" }}>{progress.error}</p>
        <p>Check the server logs for details.</p>
        {projectId && (
          <button
            onClick={async () => {
              try {
                await api.startPipeline(projectId);
                window.location.reload();
              } catch {
                // startPipeline error will show on the reloaded page
                window.location.reload();
              }
            }}
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  if (progress.isComplete) {
    return (
      <div>
        <h2>Video Complete</h2>
        <p>Your story video is ready.</p>
        {projectId && (
          <>
            <video
              controls
              style={{ maxWidth: "100%" }}
              src={`/api/v1/projects/${projectId}/artifacts/video_assembly/final.mp4`}
            />
            <a
              href={`/api/v1/projects/${projectId}/artifacts/video_assembly/final.mp4`}
              download
            >
              Download Video
            </a>
          </>
        )}
      </div>
    );
  }

  if (progress.checkpoint && projectId) {
    return <ReviewScreen projectId={projectId} checkpoint={progress.checkpoint} />;
  }

  return (
    <div>
      <h2>Processing</h2>
      {progress.currentPhase ? (
        <p>
          Current phase: <strong>{progress.currentPhase.replace(/_/g, " ")}</strong>
        </p>
      ) : (
        <p>Starting pipeline...</p>
      )}
      {progress.currentPhase && progress.scenesTotal > 0 && (
        <ProgressBar
          phase={progress.currentPhase}
          scenesDone={progress.scenesDone}
          scenesTotal={progress.scenesTotal}
        />
      )}
      <div style={{ background: "#f0f0f0", borderRadius: 4, padding: "0.5rem", marginTop: "1rem" }}>
        {progress.events.map((evt, i) => (
          <div key={i} style={{ fontSize: "0.9rem", marginBottom: "0.25rem" }}>
            <strong>{evt.event}</strong>: {JSON.stringify(evt.data)}
          </div>
        ))}
      </div>
    </div>
  );
}

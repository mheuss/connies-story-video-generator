interface Props {
  phase: string;
  scenesDone: number;
  scenesTotal: number;
}

const keyframes = `
@keyframes progress-shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
@keyframes progress-indeterminate {
  0% { left: -30%; }
  100% { left: 100%; }
}
`;

export default function ProgressBar({ phase, scenesDone, scenesTotal }: Props) {
  const phaseName = phase.replace(/_/g, " ");
  const indeterminate = scenesTotal === 0;
  const pct = indeterminate ? 0 : (scenesDone / scenesTotal) * 100;
  const isActive = indeterminate || scenesDone < scenesTotal;

  return (
    <div style={{ marginBottom: "1rem" }}>
      {isActive && <style>{keyframes}</style>}
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
        <span style={{ textTransform: "capitalize" }}>{phaseName}</span>
        {indeterminate ? (
          <span>Working...</span>
        ) : (
          <span>{scenesDone} / {scenesTotal}</span>
        )}
      </div>
      <div
        role="progressbar"
        aria-valuenow={indeterminate ? undefined : scenesDone}
        aria-valuemin={0}
        aria-valuemax={indeterminate ? undefined : scenesTotal}
        style={{
          background: "#e0e0e0",
          borderRadius: 4,
          height: 20,
          overflow: "hidden",
          position: "relative",
        }}
      >
        {indeterminate ? (
          <div
            style={{
              position: "absolute",
              height: "100%",
              width: "30%",
              borderRadius: 4,
              background: "linear-gradient(90deg, #4caf50 25%, #66bb6a 50%, #4caf50 75%)",
              animation: "progress-indeterminate 1.5s ease-in-out infinite",
            }}
          />
        ) : (
          <div
            style={{
              height: "100%",
              width: `${pct}%`,
              transition: "width 0.3s ease",
              ...(isActive
                ? {
                    background: "linear-gradient(90deg, #4caf50 25%, #66bb6a 50%, #4caf50 75%)",
                    backgroundSize: "200% 100%",
                    animation: "progress-shimmer 1.5s ease-in-out infinite",
                  }
                : { background: "#4caf50" }),
            }}
          />
        )}
      </div>
    </div>
  );
}

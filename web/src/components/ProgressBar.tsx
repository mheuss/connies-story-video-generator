interface Props {
  phase: string;
  scenesDone: number;
  scenesTotal: number;
}

export default function ProgressBar({ phase, scenesDone, scenesTotal }: Props) {
  const pct = scenesTotal > 0 ? (scenesDone / scenesTotal) * 100 : 0;
  const phaseName = phase.replace(/_/g, " ");

  return (
    <div style={{ marginBottom: "1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
        <span style={{ textTransform: "capitalize" }}>{phaseName}</span>
        <span>{scenesDone} / {scenesTotal}</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={scenesDone}
        aria-valuemin={0}
        aria-valuemax={scenesTotal}
        style={{
          background: "#e0e0e0",
          borderRadius: 4,
          height: 20,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            background: "#4caf50",
            height: "100%",
            width: `${pct}%`,
            transition: "width 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}

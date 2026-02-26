interface Props {
  projectId: string;
  checkpoint: { phase: string; project_id: string };
}

export default function ReviewScreen({ projectId, checkpoint }: Props) {
  return (
    <div>
      <h2>Review: {checkpoint.phase.replace(/_/g, " ")}</h2>
      <p>Project: {projectId}</p>
      <p>Checkpoint review UI coming next...</p>
    </div>
  );
}

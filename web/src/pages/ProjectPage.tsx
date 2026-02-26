import { useParams } from "react-router-dom";

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  return <div>Project: {projectId}</div>;
}

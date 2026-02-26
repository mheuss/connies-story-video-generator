import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ArtifactFile } from "../api/types";

interface Props {
  projectId: string;
  checkpoint: { phase: string; project_id: string };
}

export default function ReviewScreen({ projectId, checkpoint }: Props) {
  const [files, setFiles] = useState<ArtifactFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  useEffect(() => {
    api
      .listArtifacts(projectId, checkpoint.phase)
      .then((result) => setFiles(result.files))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load artifacts"))
      .finally(() => setLoading(false));
  }, [projectId, checkpoint.phase]);

  const handleApprove = async () => {
    setApproving(true);
    try {
      await api.approvePipeline(projectId);
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve");
      setApproving(false);
    }
  };

  const handleEdit = async (filename: string) => {
    try {
      const url = api.getArtifactUrl(projectId, checkpoint.phase, filename);
      const response = await fetch(url);
      const text = await response.text();
      setEditContent(text);
      setEditingFile(filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load artifact");
    }
  };

  const handleSave = async () => {
    if (!editingFile || !editContent.trim()) return;
    try {
      await api.updateArtifact(projectId, checkpoint.phase, editingFile, editContent);
      setEditingFile(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    }
  };

  if (loading) return <p>Loading artifacts...</p>;

  const phaseName = checkpoint.phase.replace(/_/g, " ");

  return (
    <div>
      <h2>Review: {phaseName}</h2>
      <p>The pipeline is waiting for your review. Check the artifacts below, make edits if needed, then approve to continue.</p>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {editingFile ? (
        <div style={{ marginBottom: "1rem" }}>
          <h3>Editing: {editingFile}</h3>
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            rows={20}
            style={{ width: "100%", fontFamily: "monospace", padding: "0.5rem" }}
          />
          <div style={{ marginTop: "0.5rem" }}>
            <button onClick={handleSave} disabled={!editContent.trim()} style={{ marginRight: "0.5rem" }}>Save</button>
            <button onClick={() => setEditingFile(null)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div style={{ marginBottom: "1rem" }}>
          {files.length === 0 ? (
            <p>No artifacts for this phase yet.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {files.map((file) => (
                <li
                  key={file.name}
                  style={{
                    padding: "0.5rem",
                    borderBottom: "1px solid #eee",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span>{file.name}</span>
                  <span style={{ fontSize: "0.8rem", color: "#666" }}>
                    {(file.size / 1024).toFixed(1)} KB
                    {file.content_type.startsWith("text/") || file.content_type === "application/json" ? (
                      <button onClick={() => handleEdit(file.name)} style={{ marginLeft: "0.5rem" }}>
                        Edit
                      </button>
                    ) : file.content_type.startsWith("image/") ? (
                      <img
                        src={api.getArtifactUrl(projectId, checkpoint.phase, file.name)}
                        alt={file.name}
                        style={{ maxWidth: 200, maxHeight: 150, marginLeft: "0.5rem" }}
                      />
                    ) : file.content_type.startsWith("audio/") ? (
                      <audio
                        controls
                        src={api.getArtifactUrl(projectId, checkpoint.phase, file.name)}
                        style={{ marginLeft: "0.5rem" }}
                      />
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <button onClick={handleApprove} disabled={approving} style={{ fontSize: "1.1rem", padding: "0.5rem 1.5rem" }}>
        {approving ? "Approving..." : "Approve & Continue"}
      </button>
    </div>
  );
}

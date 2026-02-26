import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import ApiKeySetup from "../components/ApiKeySetup";

type Mode = "adapt" | "original" | "inspired_by";

export default function CreatePage() {
  const navigate = useNavigate();
  const [keysReady, setKeysReady] = useState(false);
  const [mode, setMode] = useState<Mode>("adapt");
  const [sourceText, setSourceText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const handleKeysComplete = useCallback(() => setKeysReady(true), []);

  if (!keysReady) {
    return <ApiKeySetup onComplete={handleKeysComplete} />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sourceText.trim()) return;

    setError(null);
    setCreating(true);

    try {
      const project = await api.createProject({ mode, source_text: sourceText });
      await api.startPipeline(project.project_id);
      navigate(`/project/${project.project_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
      setCreating(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>Create a new story video</h2>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="mode">Mode</label>
        <br />
        <select
          id="mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
          style={{ padding: "0.5rem" }}
        >
          <option value="adapt">Adapt (narrate an existing story)</option>
          <option value="original">Original (write from a topic)</option>
          <option value="inspired_by">Inspired By (new story from existing)</option>
        </select>
      </div>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="source-text">
          {mode === "adapt" ? "Paste your story" : "Describe your idea"}
        </label>
        <br />
        <textarea
          id="source-text"
          value={sourceText}
          onChange={(e) => setSourceText(e.target.value)}
          rows={12}
          style={{ width: "100%", padding: "0.5rem" }}
          placeholder={mode === "adapt" ? "Paste the full text of your story here..." : "Describe your story idea..."}
        />
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      <button type="submit" disabled={creating || !sourceText.trim()}>
        {creating ? "Creating..." : "Create & Start"}
      </button>
    </form>
  );
}

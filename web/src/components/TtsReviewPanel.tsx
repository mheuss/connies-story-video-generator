import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { TtsScene } from "../api/types";

interface TtsReviewPanelProps {
  projectId: string;
}

export default function TtsReviewPanel({ projectId }: TtsReviewPanelProps) {
  const [scenes, setScenes] = useState<TtsScene[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedScenes, setExpandedScenes] = useState<Set<number>>(new Set());
  const [editingScenes, setEditingScenes] = useState<Set<number>>(new Set());
  const [editTexts, setEditTexts] = useState<Map<number, string>>(new Map());
  const [regenerating, setRegenerating] = useState<Set<number>>(new Set());
  const [sceneErrors, setSceneErrors] = useState<Map<number, string>>(new Map());

  useEffect(() => {
    api
      .getTtsScenes(projectId)
      .then((result) => setScenes(result.scenes))
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load TTS scenes"),
      )
      .finally(() => setLoading(false));
  }, [projectId]);

  const toggleExpanded = (sceneNumber: number) => {
    setExpandedScenes((prev) => {
      const next = new Set(prev);
      if (next.has(sceneNumber)) {
        next.delete(sceneNumber);
      } else {
        next.add(sceneNumber);
      }
      return next;
    });
  };

  const startEditing = (scene: TtsScene) => {
    setEditTexts((prev) => new Map(prev).set(scene.scene_number, scene.narration_text));
    setEditingScenes((prev) => new Set(prev).add(scene.scene_number));
  };

  const cancelEditing = (sceneNumber: number) => {
    setEditingScenes((prev) => {
      const next = new Set(prev);
      next.delete(sceneNumber);
      return next;
    });
    setEditTexts((prev) => {
      const next = new Map(prev);
      next.delete(sceneNumber);
      return next;
    });
  };

  const handleSave = async (sceneNumber: number) => {
    const text = editTexts.get(sceneNumber);
    if (text === undefined) return;

    // Clear any previous error for this scene
    setSceneErrors((prev) => {
      const next = new Map(prev);
      next.delete(sceneNumber);
      return next;
    });

    try {
      const updated = await api.updateNarrationText(projectId, sceneNumber, text);
      setScenes((prev) =>
        prev.map((s) => (s.scene_number === sceneNumber ? updated : s)),
      );
      cancelEditing(sceneNumber);
    } catch (err) {
      setSceneErrors((prev) =>
        new Map(prev).set(
          sceneNumber,
          err instanceof Error ? err.message : "Failed to save narration text",
        ),
      );
    }
  };

  const handleRegenerate = async (sceneNumber: number) => {
    // Clear any previous error for this scene
    setSceneErrors((prev) => {
      const next = new Map(prev);
      next.delete(sceneNumber);
      return next;
    });

    setRegenerating((prev) => new Set(prev).add(sceneNumber));

    try {
      const updated = await api.regenerateTtsScene(projectId, sceneNumber);
      // Bust audio cache by appending timestamp
      const bustedUrl = updated.audio_url.includes("?")
        ? `${updated.audio_url}&t=${Date.now()}`
        : `${updated.audio_url}?t=${Date.now()}`;
      setScenes((prev) =>
        prev.map((s) =>
          s.scene_number === sceneNumber ? { ...updated, audio_url: bustedUrl } : s,
        ),
      );
    } catch (err) {
      setSceneErrors((prev) =>
        new Map(prev).set(
          sceneNumber,
          err instanceof Error ? err.message : "Failed to regenerate audio",
        ),
      );
    } finally {
      setRegenerating((prev) => {
        const next = new Set(prev);
        next.delete(sceneNumber);
        return next;
      });
    }
  };

  if (loading) return <p>Loading audio scenes...</p>;

  if (error) return <p style={{ color: "red" }}>{error}</p>;

  return (
    <div>
      {scenes.map((scene) => {
        const isExpanded = expandedScenes.has(scene.scene_number);
        const isEditing = editingScenes.has(scene.scene_number);
        const isRegenerating = regenerating.has(scene.scene_number);
        const sceneError = sceneErrors.get(scene.scene_number);

        return (
          <div
            key={scene.scene_number}
            style={{
              padding: "0.75rem",
              borderBottom: "1px solid #eee",
              marginBottom: "0.5rem",
            }}
          >
            <h3>
              Scene {scene.scene_number}: {scene.title}
            </h3>

            {scene.has_audio ? (
              <audio
                controls
                src={scene.audio_url}
                style={{ width: "100%", marginTop: "0.5rem" }}
              />
            ) : (
              <p>No audio generated</p>
            )}

            {isRegenerating && <p>Regenerating...</p>}

            {sceneError && (
              <p style={{ color: "red", fontSize: "0.85rem" }}>{sceneError}</p>
            )}

            <div style={{ marginTop: "0.5rem" }}>
              <button onClick={() => toggleExpanded(scene.scene_number)}>
                {isExpanded ? "Hide text" : "Show text"}
              </button>
              <button
                onClick={() => handleRegenerate(scene.scene_number)}
                disabled={isRegenerating}
                style={{ marginLeft: "0.5rem" }}
              >
                Regenerate
              </button>
            </div>

            {isExpanded && (
              <div style={{ marginTop: "0.5rem" }}>
                <textarea
                  value={
                    isEditing
                      ? (editTexts.get(scene.scene_number) ?? "")
                      : scene.narration_text
                  }
                  readOnly={!isEditing}
                  onChange={(e) => {
                    if (isEditing) {
                      setEditTexts((prev) =>
                        new Map(prev).set(scene.scene_number, e.target.value),
                      );
                    }
                  }}
                  rows={8}
                  style={{
                    width: "100%",
                    fontFamily: "monospace",
                    padding: "0.5rem",
                  }}
                />
                <div style={{ marginTop: "0.5rem" }}>
                  {isEditing ? (
                    <>
                      <button
                        onClick={() => handleSave(scene.scene_number)}
                        style={{ marginRight: "0.5rem" }}
                      >
                        Save
                      </button>
                      <button onClick={() => cancelEditing(scene.scene_number)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button onClick={() => startEditing(scene)}>Edit</button>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { TtsScene } from "../api/types";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";
import { Textarea } from "./ui/textarea";

interface TtsReviewPanelProps {
  projectId: string;
  onNarrationEdited?: () => void;
}

export default function TtsReviewPanel({
  projectId,
  onNarrationEdited,
}: TtsReviewPanelProps) {
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
      onNarrationEdited?.();
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

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading audio scenes...</p>;
  }

  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

  return (
    <div className="space-y-3">
      {scenes.map((scene) => {
        const isExpanded = expandedScenes.has(scene.scene_number);
        const isEditing = editingScenes.has(scene.scene_number);
        const isRegenerating = regenerating.has(scene.scene_number);
        const sceneError = sceneErrors.get(scene.scene_number);

        return (
          <Card key={scene.scene_number} size="sm">
            <CardHeader>
              <h3 className="text-sm font-medium">
                Scene {scene.scene_number}: {scene.title}
              </h3>
            </CardHeader>

            <CardContent className="space-y-3">
              {scene.has_audio ? (
                <audio
                  controls
                  src={scene.audio_url}
                  className="w-full"
                  aria-label={`Audio for scene ${scene.scene_number}`}
                />
              ) : (
                <p className="text-sm text-muted-foreground">No audio generated</p>
              )}

              {isRegenerating && (
                <p className="text-sm text-muted-foreground">Regenerating...</p>
              )}

              {sceneError && (
                <p className="text-sm text-destructive">{sceneError}</p>
              )}

              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => toggleExpanded(scene.scene_number)}
                >
                  {isExpanded ? "Hide text" : "Show text"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleRegenerate(scene.scene_number)}
                  disabled={isRegenerating}
                >
                  Regenerate
                </Button>
              </div>

              {isExpanded && (
                <div className="space-y-2">
                  <label
                    htmlFor={`narration-${scene.scene_number}`}
                    className="sr-only"
                  >
                    Narration text for scene {scene.scene_number}
                  </label>
                  <Textarea
                    id={`narration-${scene.scene_number}`}
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
                    className="font-mono text-sm"
                  />
                  <div className="flex gap-2">
                    {isEditing ? (
                      <>
                        <Button
                          size="sm"
                          onClick={() => handleSave(scene.scene_number)}
                        >
                          Save
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => cancelEditing(scene.scene_number)}
                        >
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => startEditing(scene)}
                      >
                        Edit
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

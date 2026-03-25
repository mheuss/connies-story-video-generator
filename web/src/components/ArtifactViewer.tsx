import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ArtifactFile } from "../api/types";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

export interface ArtifactViewerProps {
  projectId: string;
  phase: string;
  editable?: boolean;
  onEdited?: (phase: string) => void;
}

/** Strip parameters from MIME type (e.g. "application/json; charset=utf-8" → "application/json"). */
function mimeBase(contentType: string): string {
  return contentType.split(";", 1)[0].trim().toLowerCase();
}

/** Returns true for content types that support inline editing. */
function isEditable(contentType: string): boolean {
  const mime = mimeBase(contentType);
  return mime.startsWith("text/") || mime === "application/json";
}

/** Returns true for image content types. */
function isImage(contentType: string): boolean {
  return mimeBase(contentType).startsWith("image/");
}

/** Returns true for audio content types. */
function isAudio(contentType: string): boolean {
  return mimeBase(contentType).startsWith("audio/");
}

/** Formats a byte count into a human-readable size string. */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export function ArtifactViewer({
  projectId,
  phase,
  editable = false,
  onEdited,
}: ArtifactViewerProps) {
  const [files, setFiles] = useState<ArtifactFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let stale = false;
    setLoading(true);
    setLoadError(null);
    setActionError(null);
    api
      .listArtifacts(projectId, phase)
      .then((result) => {
        if (!stale) setFiles(result.files);
      })
      .catch((err) => {
        if (!stale)
          setLoadError(err instanceof Error ? err.message : "Failed to load artifacts");
      })
      .finally(() => {
        if (!stale) setLoading(false);
      });
    return () => { stale = true; };
  }, [projectId, phase]);

  const handleEdit = async (filename: string) => {
    setActionError(null);
    try {
      const url = api.getArtifactUrl(projectId, phase, filename);
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to fetch ${filename}`);
      }
      const text = await response.text();
      setEditContent(text);
      setEditingFile(filename);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to load file content");
    }
  };

  const handleSave = async () => {
    if (!editingFile) return;
    setSaving(true);
    setActionError(null);
    try {
      await api.updateArtifact(projectId, phase, editingFile, editContent);
      setEditingFile(null);
      setEditContent("");
      onEdited?.(phase);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditingFile(null);
    setEditContent("");
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading artifacts...</p>;
  }

  if (loadError) {
    return <p className="text-sm text-destructive">{loadError}</p>;
  }

  if (files.length === 0) {
    return <p className="text-sm text-muted-foreground">No artifacts for this phase.</p>;
  }

  return (
    <>
      {actionError && (
        <p className="mb-2 text-sm text-destructive">{actionError}</p>
      )}
      <ul className="divide-y divide-border" role="list">
      {files.map((file) => (
        <li key={file.name} className="py-3 first:pt-0 last:pb-0">
          {editingFile === file.name ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-foreground">
                  {file.name}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatSize(file.size)}
                </span>
              </div>
              <label htmlFor={`edit-${file.name}`} className="sr-only">
                Edit content of {file.name}
              </label>
              <Textarea
                id={`edit-${file.name}`}
                aria-label={`Edit content of ${file.name}`}
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                rows={12}
                className="font-mono text-sm"
              />
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? "Saving..." : "Save"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCancel}
                  disabled={saving}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0 flex-1">
                <span className="text-sm font-medium text-foreground">
                  {file.name}
                </span>
                <span className="ml-2 text-xs text-muted-foreground">
                  {formatSize(file.size)}
                </span>
              </div>

              <div className="flex shrink-0 items-center gap-2">
                {isImage(file.content_type) && (
                  <img
                    src={api.getArtifactUrl(projectId, phase, file.name)}
                    alt={`Artifact thumbnail for ${file.name}`}
                    className="max-h-24 max-w-48 rounded border border-border object-contain"
                  />
                )}

                {isAudio(file.content_type) && (
                  <audio
                    controls
                    src={api.getArtifactUrl(projectId, phase, file.name)}
                    aria-label={`Audio player for ${file.name}`}
                  />
                )}

                {editable && isEditable(file.content_type) && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleEdit(file.name)}
                  >
                    Edit
                  </Button>
                )}
              </div>
            </div>
          )}
        </li>
      ))}
    </ul>
    </>
  );
}

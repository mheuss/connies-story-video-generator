/** API key configuration status. */
export interface ApiKeyStatus {
  anthropic_configured: boolean;
  openai_configured: boolean;
}

/** Request body for setting API keys. */
export interface SetApiKeysRequest {
  anthropic_api_key?: string;
  openai_api_key?: string;
}

/** Request body for creating a project. */
export interface CreateProjectRequest {
  mode: "original" | "inspired_by" | "adapt";
  source_text: string;
}

/** Response from creating a project. */
export interface CreateProjectResponse {
  project_id: string;
  mode: string;
  project_dir: string;
}

/** Project status response. */
export interface ProjectStatus {
  project_id: string;
  mode: string;
  status:
    | "pending"
    | "in_progress"
    | "completed"
    | "awaiting_review"
    | "failed";
  current_phase: string | null;
  scene_count: number;
  created_at: string;
}

/** Artifact file metadata. */
export interface ArtifactFile {
  name: string;
  size: number;
  content_type: string;
}

/** Artifact list response. */
export interface ArtifactList {
  files: ArtifactFile[];
}

/** SSE event from the progress endpoint. */
export interface ProgressEvent {
  event: "phase_started" | "scene_progress" | "checkpoint" | "completed" | "error";
  data: Record<string, unknown>;
}

/** API key configuration status. */
export interface ApiKeyStatus {
  anthropic_configured: boolean;
  openai_configured: boolean;
  elevenlabs_configured: boolean;
}

/** Request body for setting API keys. */
export interface SetApiKeysRequest {
  anthropic_api_key?: string;
  openai_api_key?: string;
  elevenlabs_api_key?: string;
}

/** Request body for creating a project. */
export interface CreateProjectRequest {
  mode: "original" | "inspired_by" | "adapt";
  source_text: string;
  autonomous?: boolean;
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

/** Project summary for list view. */
export interface ProjectSummary {
  project_id: string;
  mode: string;
  status: "pending" | "in_progress" | "completed" | "awaiting_review" | "failed";
  current_phase: string | null;
  scene_count: number;
  created_at: string;
  source_text_preview: string;
}

/** Response from listing projects. */
export interface ListProjectsResponse {
  projects: ProjectSummary[];
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

/** TTS scene metadata for audio review. */
export interface TtsScene {
  scene_number: number;
  title: string;
  narration_text: string;
  audio_file: string;
  audio_url: string;
  has_audio: boolean;
}

/** TTS scene list response. */
export interface TtsSceneList {
  scenes: TtsScene[];
}

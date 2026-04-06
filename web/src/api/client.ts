import type {
  ApiKeyStatus,
  ArtifactList,
  CreateProjectRequest,
  CreateProjectResponse,
  ListProjectsResponse,
  ProjectStatus,
  RerunResponse,
  SetApiKeysRequest,
  TtsScene,
  TtsSceneList,
} from "./types";

const BASE = "/api/v1";

/** Error thrown when the API returns a non-OK response. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Network error — is the backend running?", {
        cause: error,
      });
    }
    throw error;
  }

  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Request failed" }));
    throw new ApiError(response.status, body.detail || "Request failed");
  }

  return response.json() as Promise<T>;
}

function validateArtifactContent(filename: string, content: string): void {
  if (!filename.toLowerCase().endsWith(".json")) return;

  try {
    JSON.parse(content);
  } catch {
    throw new Error("Content must be valid JSON");
  }
}

export const api = {
  // Health
  getHealth: () => request<{ status: string }>("/health", { method: "GET" }),

  // Settings
  getApiKeyStatus: () =>
    request<ApiKeyStatus>("/settings/api-keys", { method: "GET" }),

  setApiKeys: (keys: SetApiKeysRequest) =>
    request<{ status: string }>("/settings/api-keys", {
      method: "POST",
      body: JSON.stringify(keys),
    }),

  // Projects
  listProjects: () =>
    request<ListProjectsResponse>("/projects", { method: "GET" }),

  createProject: (data: CreateProjectRequest) =>
    request<CreateProjectResponse>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getProject: (projectId: string) =>
    request<ProjectStatus>(`/projects/${projectId}`, { method: "GET" }),

  deleteProject: (projectId: string) =>
    request<{ status: string }>(`/projects/${projectId}`, {
      method: "DELETE",
    }),

  // Pipeline
  startPipeline: (projectId: string) =>
    request<{ status: string }>(`/projects/${projectId}/start`, {
      method: "POST",
    }),

  approvePipeline: (projectId: string, auto?: boolean) =>
    request<{ status: string }>(`/projects/${projectId}/approve`, {
      method: "POST",
      ...(auto !== undefined ? { body: JSON.stringify({ auto }) } : {}),
    }),

  rerunFromPhase: (projectId: string, phase: string) =>
    request<RerunResponse>(
      `/projects/${encodeURIComponent(projectId)}/rerun-from/${encodeURIComponent(phase)}`,
      { method: "POST" },
    ),

  // Artifacts
  listArtifacts: (projectId: string, phase: string) =>
    request<ArtifactList>(
      `/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(phase)}`,
      { method: "GET" },
    ),

  getArtifactText: async (projectId: string, phase: string, filename: string) => {
    const MAX_EDIT_SIZE = 1_048_576; // 1 MB

    let response: Response;

    try {
      response = await fetch(
        `${BASE}/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(phase)}/${encodeURIComponent(filename)}`,
      );
    } catch (error) {
      if (error instanceof TypeError) {
        throw new Error("Network error — is the backend running?", {
          cause: error,
        });
      }
      throw error;
    }

    if (!response.ok) {
      throw new ApiError(response.status, `Failed to fetch ${filename}`);
    }

    const contentLength = response.headers.get("content-length");
    if (contentLength && parseInt(contentLength, 10) > MAX_EDIT_SIZE) {
      throw new Error(
        `File is too large to edit in the browser (${(parseInt(contentLength, 10) / 1_048_576).toFixed(1)} MB). Max: 1 MB.`,
      );
    }

    return response.text();
  },

  getArtifactUrl: (projectId: string, phase: string, filename: string) =>
    `${BASE}/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(phase)}/${encodeURIComponent(filename)}`,

  updateArtifact: async (
    projectId: string,
    phase: string,
    filename: string,
    content: string,
  ) => {
    validateArtifactContent(filename, content);
    return request<{ status: string; filename: string }>(
      `/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(phase)}/${encodeURIComponent(filename)}`,
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    );
  },

  // TTS Review
  getTtsScenes: (projectId: string) =>
    request<TtsSceneList>(`/projects/${projectId}/tts-scenes`, { method: "GET" }),

  regenerateTtsScene: (projectId: string, sceneNumber: number) =>
    request<TtsScene>(`/projects/${projectId}/tts-scenes/${sceneNumber}/regenerate`, {
      method: "POST",
    }),

  updateNarrationText: (projectId: string, sceneNumber: number, text: string) =>
    request<TtsScene>(`/projects/${projectId}/tts-scenes/${sceneNumber}/narration-text`, {
      method: "PUT",
      body: JSON.stringify({ narration_text: text }),
    }),
};

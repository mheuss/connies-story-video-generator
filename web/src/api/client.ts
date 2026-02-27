import type {
  ApiKeyStatus,
  ArtifactList,
  CreateProjectRequest,
  CreateProjectResponse,
  ProjectStatus,
  SetApiKeysRequest,
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
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Request failed" }));
    throw new ApiError(response.status, body.detail || "Request failed");
  }

  return response.json() as Promise<T>;
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
      body: JSON.stringify(auto ? { auto: true } : {}),
    }),

  // Artifacts
  listArtifacts: (projectId: string, phase: string) =>
    request<ArtifactList>(`/projects/${projectId}/artifacts/${phase}`, {
      method: "GET",
    }),

  getArtifactUrl: (projectId: string, phase: string, filename: string) =>
    `${BASE}/projects/${projectId}/artifacts/${phase}/${filename}`,

  updateArtifact: (
    projectId: string,
    phase: string,
    filename: string,
    content: string,
  ) =>
    request<{ status: string; filename: string }>(
      `/projects/${projectId}/artifacts/${phase}/${filename}`,
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    ),
};

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ProjectSummary } from "../api/types";

/**
 * Status colors chosen to meet WCAG AA contrast ratio (4.5:1)
 * against a white (#fff) background.
 */
const STATUS_COLORS: Record<string, string> = {
  completed: "#15803d",
  in_progress: "#a16207",
  awaiting_review: "#a16207",
  failed: "#dc2626",
  pending: "#6b7280",
};

function formatDate(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;
  return date.toLocaleDateString();
}

function formatPhase(phase: string | null): string {
  if (!phase) return "";
  return phase
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ProjectListPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then((res) => setProjects(res.projects))
      .catch((err) => setError(err.message || "Failed to load projects"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <p>Loading projects...</p>;
  }

  if (error) {
    return <p>Failed to load projects: {error}</p>;
  }

  if (projects.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: "3rem 1rem" }}>
        <h2>No projects yet</h2>
        <p>Create your first project to get started.</p>
        <Link
          to="/create"
          style={{
            display: "inline-block",
            padding: "0.75rem 1.5rem",
            background: "#2563eb",
            color: "#fff",
            borderRadius: "6px",
            textDecoration: "none",
            fontWeight: 600,
          }}
        >
          Create Project
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1.5rem",
        }}
      >
        <h2 style={{ margin: 0 }}>Projects</h2>
        <Link
          to="/create"
          style={{
            padding: "0.5rem 1rem",
            background: "#2563eb",
            color: "#fff",
            borderRadius: "6px",
            textDecoration: "none",
            fontWeight: 600,
            fontSize: "0.9rem",
          }}
        >
          Create New
        </Link>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {projects.map((project) => (
          <Link
            key={project.project_id}
            to={`/project/${project.project_id}`}
            style={{
              display: "block",
              padding: "1rem",
              border: "1px solid #e5e7eb",
              borderRadius: "8px",
              textDecoration: "none",
              color: "inherit",
              transition: "border-color 0.15s",
            }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.borderColor = "#2563eb")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.borderColor = "#e5e7eb")
            }
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "0.5rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span
                  style={{
                    padding: "0.2rem 0.5rem",
                    background: "#f3f4f6",
                    borderRadius: "4px",
                    fontSize: "0.8rem",
                    fontWeight: 600,
                  }}
                >
                  {project.mode}
                </span>
                <span
                  style={{
                    color: STATUS_COLORS[project.status] || "#6b7280",
                    fontSize: "0.85rem",
                    fontWeight: 500,
                  }}
                >
                  {project.status.replace(/_/g, " ")}
                </span>
              </div>
              <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>
                {formatDate(project.created_at)}
              </span>
            </div>
            <div style={{ display: "flex", gap: "1rem", fontSize: "0.85rem", color: "#6b7280" }}>
              {project.current_phase && (
                <span>{formatPhase(project.current_phase)}</span>
              )}
              {project.scene_count > 0 && (
                <span>{project.scene_count} scenes</span>
              )}
            </div>
            {project.source_text_preview && (
              <p
                style={{
                  margin: "0.5rem 0 0",
                  fontSize: "0.85rem",
                  color: "#6b7280",
                  lineHeight: 1.4,
                }}
              >
                {project.source_text_preview}
              </p>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}

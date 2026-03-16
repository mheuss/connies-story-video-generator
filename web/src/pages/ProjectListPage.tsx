import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ProjectSummary } from "../api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

/** Maps project status to a shadcn Badge variant for consistent styling. */
const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  completed: "default",
  in_progress: "secondary",
  awaiting_review: "secondary",
  failed: "destructive",
  pending: "outline",
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
      <div className="text-center py-12 px-4">
        <h2 className="text-lg font-semibold mb-2">No projects yet</h2>
        <p className="text-muted-foreground mb-6">Create your first project to get started.</p>
        <Link
          to="/create"
          className="inline-block px-6 py-3 bg-primary text-primary-foreground rounded-lg font-semibold no-underline hover:bg-primary/80"
        >
          Create Project
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-lg font-semibold">Projects</h2>
        <Link
          to="/create"
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg font-semibold text-sm no-underline hover:bg-primary/80"
        >
          Create New
        </Link>
      </div>
      <div className="flex flex-col gap-3">
        {projects.map((project) => {
          const badgeVariant = STATUS_VARIANT[project.status] || STATUS_VARIANT.pending;
          return (
            <Link
              key={project.project_id}
              to={`/project/${project.project_id}`}
              className="block no-underline text-foreground"
            >
              <Card className="transition-colors hover:ring-primary/40">
                <CardContent>
                  <div className="flex justify-between items-center mb-2">
                    <div className="flex items-center gap-3">
                      <Badge variant="secondary">{project.mode}</Badge>
                      <Badge variant={badgeVariant}>
                        {project.status.replace(/_/g, " ")}
                      </Badge>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(project.created_at)}
                    </span>
                  </div>
                  <div className="flex gap-4 text-sm text-muted-foreground">
                    {project.current_phase && (
                      <span>{formatPhase(project.current_phase)}</span>
                    )}
                    {project.scene_count > 0 && (
                      <span>{project.scene_count} scenes</span>
                    )}
                  </div>
                  {project.source_text_preview && (
                    <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                      {project.source_text_preview}
                    </p>
                  )}
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

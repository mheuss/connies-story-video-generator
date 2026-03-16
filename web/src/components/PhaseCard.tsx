import { ReactNode } from "react";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { PhaseStatus } from "@/data/phases";

interface PhaseCardProps {
  phase: string;
  label: string;
  status: PhaseStatus;
  error?: string;
  onRetry?: () => void;
  children?: ReactNode;
}

const STATUS_CONFIG: Record<
  PhaseStatus,
  {
    badgeLabel: string;
    badgeVariant: "default" | "secondary" | "destructive" | "outline";
    icon: string;
    iconClass: string;
  }
> = {
  completed: {
    badgeLabel: "Completed",
    badgeVariant: "default",
    icon: "\u2713",
    iconClass: "text-green-600 bg-green-100 border-green-300",
  },
  running: {
    badgeLabel: "Running...",
    badgeVariant: "secondary",
    icon: "\u25CB",
    iconClass: "text-blue-600 bg-blue-100 border-blue-300 animate-spin",
  },
  checkpoint: {
    badgeLabel: "Awaiting review",
    badgeVariant: "outline",
    icon: "\u23F0",
    iconClass: "text-orange-600 bg-orange-100 border-orange-300",
  },
  stale: {
    badgeLabel: "Stale",
    badgeVariant: "secondary",
    icon: "\u26A0",
    iconClass: "text-yellow-600 bg-yellow-100 border-yellow-300",
  },
  pending: {
    badgeLabel: "Pending",
    badgeVariant: "secondary",
    icon: "\uD83D\uDD12",
    iconClass: "text-gray-400 bg-gray-100 border-gray-300",
  },
  failed: {
    badgeLabel: "Failed",
    badgeVariant: "destructive",
    icon: "\u2717",
    iconClass: "text-red-600 bg-red-100 border-red-300",
  },
};

/** Whether this status forces the card body to always be visible. */
function isAlwaysExpanded(status: PhaseStatus): boolean {
  return status === "checkpoint" || status === "failed";
}

/** Whether this status supports expanding/collapsing. */
function isCollapsible(status: PhaseStatus): boolean {
  return status === "completed" || status === "stale";
}

/** Whether this status has a visible body at all. */
function hasBody(status: PhaseStatus): boolean {
  return status !== "pending";
}

export function PhaseCard({
  phase,
  label,
  status,
  error,
  onRetry,
  children,
}: PhaseCardProps) {
  const config = STATUS_CONFIG[status];
  const alwaysExpanded = isAlwaysExpanded(status);
  const collapsible = isCollapsible(status);

  // Build the header content shared by all states.
  const headerContent = (
    <CardHeader className="flex flex-col gap-1 py-2">
      <div className="flex flex-row items-center gap-3">
        <span
          data-testid="phase-status-icon"
          aria-hidden="true"
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs ${config.iconClass}`}
        >
          {config.icon}
        </span>
        <span className="font-medium">{label}</span>
        <Badge variant={config.badgeVariant}>{config.badgeLabel}</Badge>
      </div>
      {status === "stale" && (
        <p className="pl-9 text-xs text-muted-foreground">
          Upstream phase was re-edited. Re-run to update.
        </p>
      )}
    </CardHeader>
  );

  // Build the body content.
  const bodyContent = (
    <CardContent>
      {status === "failed" && error && (
        <div className="mb-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {children}
      {status === "failed" && onRetry && (
        <Button
          variant="destructive"
          size="sm"
          className="mt-2"
          onClick={onRetry}
        >
          Retry
        </Button>
      )}
    </CardContent>
  );

  // Pending: header only, no body.
  if (!hasBody(status)) {
    return (
      <Card data-phase={phase} data-status={status} className="relative pl-8">
        {headerContent}
      </Card>
    );
  }

  // Always-expanded states (checkpoint, failed): show body, no collapse toggle.
  if (alwaysExpanded) {
    return (
      <Card data-phase={phase} data-status={status} className="relative pl-8">
        {headerContent}
        {bodyContent}
      </Card>
    );
  }

  // Collapsible states (completed, stale): collapsed by default.
  if (collapsible) {
    return (
      <Collapsible defaultOpen={false}>
        <Card
          data-phase={phase}
          data-status={status}
          className="relative pl-8"
        >
          <CollapsibleTrigger
            aria-label={`${label} phase, ${config.badgeLabel}`}
            className="w-full cursor-pointer text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            {headerContent}
          </CollapsibleTrigger>
          <CollapsibleContent>
            {bodyContent}
          </CollapsibleContent>
        </Card>
      </Collapsible>
    );
  }

  // Running: shows header and body (running content is minimal).
  return (
    <Card data-phase={phase} data-status={status} className="relative pl-8">
      {headerContent}
      {bodyContent}
    </Card>
  );
}

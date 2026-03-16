import { PhaseCard } from "./PhaseCard";
import {
  getPhaseSequence,
  getPhaseLabel,
  derivePhaseStatuses,
} from "@/data/phases";

interface PhaseTimelineProps {
  mode: string;
  currentPhase: string | null;
  projectStatus: string;
  renderPhaseContent?: (phase: string, status: string) => React.ReactNode;
  staleAfter?: string | null;
  onRetry?: (phase: string) => void;
  phaseErrors?: Record<string, string>;
}

export function PhaseTimeline({
  mode,
  currentPhase,
  projectStatus,
  renderPhaseContent,
  staleAfter,
  onRetry,
  phaseErrors,
}: PhaseTimelineProps) {
  const phases = getPhaseSequence(mode);
  const statuses = derivePhaseStatuses(mode, currentPhase, projectStatus);

  // Apply stale overrides if an edit has invalidated downstream.
  // The current phase is exempt — it reflects live pipeline state,
  // not a cached result that could be outdated.
  if (staleAfter) {
    const staleIdx = phases.indexOf(staleAfter);
    if (staleIdx >= 0) {
      for (let i = staleIdx + 1; i < phases.length; i++) {
        const phase = phases[i];
        if (phase === currentPhase) continue;
        if (statuses[phase] === "completed") {
          statuses[phase] = "stale";
        }
      }
    }
  }

  return (
    <ol className="relative" aria-label="Pipeline phases">
      {/* Decorative vertical timeline line */}
      <div
        className="absolute left-3 top-0 bottom-0 w-px bg-gray-300"
        aria-hidden="true"
      />

      {phases.map((phase) => (
        <li key={phase}>
          <PhaseCard
            phase={phase}
            label={getPhaseLabel(phase)}
            status={statuses[phase]}
            error={phaseErrors?.[phase]}
            onRetry={onRetry ? () => onRetry(phase) : undefined}
          >
            {renderPhaseContent?.(phase, statuses[phase])}
          </PhaseCard>
        </li>
      ))}
    </ol>
  );
}

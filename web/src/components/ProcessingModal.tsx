import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { getPhaseLabel } from "@/data/phases";

/*
 * A11y: Focus trap rationale (WCAG 2.1.2 — No Keyboard Trap)
 *
 * This modal traps focus while a pipeline phase is running. The user cannot
 * dismiss it via Escape or clicking outside. This is intentional: the phase
 * completing (or failing) is the exit mechanism. In the error state, Close and
 * Retry buttons provide keyboard-accessible exits. This meets WCAG 2.1.2
 * because the user is informed of the exit mechanism and can use standard
 * keyboard interaction (Tab to buttons, Enter/Space to activate) once an error
 * occurs.
 */

interface ProcessingModalProps {
  /** Whether the modal is visible. */
  open: boolean;
  /** The current pipeline phase ID (e.g. "tts_generation"). */
  phase: string;
  /** Status text shown below the phase title. Omitted in error state. */
  statusText?: string;
  /** When set, the modal switches to error state. */
  error?: string;
  /** Called when the user clicks the Retry button (error state only). */
  onRetry?: () => void;
  /** Called when the user clicks the Close button (error state only). */
  onClose?: () => void;
}

export function ProcessingModal({
  open,
  phase,
  statusText,
  error,
  onRetry,
  onClose,
}: ProcessingModalProps) {
  const isError = Boolean(error);
  const titleId = "processing-modal-title";
  const phaseLabel = getPhaseLabel(phase);

  return (
    <Dialog
      open={open}
      modal={true}
      disablePointerDismissal={true}
      onOpenChange={(_open, details) => {
        // Block all automatic dismissals (escape, outside click).
        // In error state, the user closes via the Close button which calls onClose directly.
        details.cancel();
      }}
    >
      <DialogContent
        showCloseButton={false}
        aria-labelledby={titleId}
      >
        <DialogHeader>
          <DialogTitle id={titleId}>{phaseLabel}</DialogTitle>
        </DialogHeader>

        {isError ? (
          <>
            <DialogDescription>
              <span className="text-destructive font-medium">{error}</span>
            </DialogDescription>
            <DialogFooter>
              <Button variant="outline" onClick={onClose}>
                Close
              </Button>
              <Button onClick={onRetry}>Retry</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <div
              role="status"
              aria-label="Processing"
              className="flex justify-center py-4"
            >
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600" />
            </div>
            <div aria-live="polite">
              <DialogDescription>
                {statusText}
              </DialogDescription>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

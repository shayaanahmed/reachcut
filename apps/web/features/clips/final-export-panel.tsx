import Link from "next/link";

import type { Project } from "../../lib/contracts";
import type { OperationState } from "../projects/use-project-workbench";
import { finalUrl } from "./api";

type Clip = Project["clips"][number];

function clipDuration(clip: Clip) {
  const slices = clip.plan.source_slices.length
    ? clip.plan.source_slices
    : [clip.plan.source];
  return slices.reduce(
    (total, slice) => total + slice.end_seconds - slice.start_seconds,
    0,
  );
}

export function FinalExportPanel({
  clip,
  publishHref,
  hasUnsavedChanges,
  approvalPending,
  renderState,
  onApprove,
  onRender,
}: {
  clip: Clip;
  publishHref: string;
  hasUnsavedChanges: boolean;
  approvalPending: boolean;
  renderState?: OperationState;
  onApprove: (clipId: string, approved: boolean) => Promise<boolean>;
  onRender: (clipId: string) => Promise<unknown>;
}) {
  const approved = clip.approval_status === "approved";
  const rendered = Boolean(clip.final_path);
  const busy = approvalPending || Boolean(renderState);
  const status = rendered
    ? "ready"
    : renderState === "working"
      ? "rendering"
      : renderState === "queued"
        ? "queued"
        : hasUnsavedChanges
          ? "changes"
          : approved
            ? "ready-to-render"
            : "approval";

  return (
    <section
      className={`final-export-panel ${status}`}
      id="final-export"
      aria-labelledby="final-export-title"
    >
      <div className="final-export-intro">
        <span className="export-icon" aria-hidden="true">
          {rendered ? "✓" : renderState ? "↻" : "↗"}
        </span>
        <div>
          <span className="eyebrow">FINAL EXPORT</span>
          <h2 id="final-export-title">
            {rendered
              ? "Your publishing master is ready"
              : renderState === "working"
                ? "Rendering your final video"
                : renderState === "queued"
                  ? "Final video is in the render queue"
                  : "Prepare the publishing master"}
          </h2>
          <p>
            {rendered
              ? "Download the MP4 or continue to the dedicated publishing workspace."
              : renderState
                ? "You can keep reviewing this page. The export status updates here automatically."
                : "ReachCut uses the saved preview settings to create a full-quality vertical MP4."}
          </p>
        </div>
      </div>

      <div className="export-readiness" aria-label="Export readiness">
        <span className={!hasUnsavedChanges ? "complete" : "attention"}>
          <i aria-hidden="true">{hasUnsavedChanges ? "1" : "✓"}</i>
          <span>
            <strong>Edits saved</strong>
            <small>
              {hasUnsavedChanges
                ? "Save preview changes first"
                : "Preview is current"}
            </small>
          </span>
        </span>
        <span className={approved ? "complete" : "attention"}>
          <i aria-hidden="true">{approved ? "✓" : "2"}</i>
          <span>
            <strong>Approved</strong>
            <small>{approved ? "Ready for export" : "Approval required"}</small>
          </span>
        </span>
        <span className={rendered ? "complete" : renderState ? "active" : ""}>
          <i aria-hidden="true">{rendered ? "✓" : "3"}</i>
          <span>
            <strong>Final MP4</strong>
            <small>
              {rendered
                ? "Available now"
                : renderState === "queued"
                  ? "Waiting for renderer"
                  : renderState === "working"
                    ? "Encoding locally"
                    : "Not rendered yet"}
            </small>
          </span>
        </span>
      </div>

      <div className="export-deliverable">
        <div>
          <span>Format</span>
          <strong>MP4 · H.264</strong>
        </div>
        <div>
          <span>Canvas</span>
          <strong>9:16 vertical</strong>
        </div>
        <div>
          <span>Duration</span>
          <strong>{clipDuration(clip).toFixed(0)} seconds</strong>
        </div>
      </div>

      <div className="export-primary-action" aria-live="polite">
        {rendered ? (
          <>
            <Link className="export-publish-link" href={publishHref}>
              Continue to publishing <span>→</span>
            </Link>
            <a className="export-download-secondary" href={finalUrl(clip.id)}>
              Download MP4
            </a>
          </>
        ) : !approved ? (
          <button
            type="button"
            disabled={busy || hasUnsavedChanges}
            onClick={() => {
              void (async () => {
                if (await onApprove(clip.id, true)) await onRender(clip.id);
              })();
            }}
          >
            {approvalPending ? "Approving clip…" : "Approve & render final MP4"}
          </button>
        ) : (
          <button
            type="button"
            disabled={busy || hasUnsavedChanges}
            onClick={() => void onRender(clip.id)}
          >
            {hasUnsavedChanges
              ? "Save preview changes first"
              : renderState === "queued"
                ? "Queued for rendering…"
                : renderState === "working"
                  ? "Rendering final MP4…"
                  : "Render final MP4"}
          </button>
        )}
        {!rendered && (
          <small>
            {hasUnsavedChanges
              ? "The final export always uses your last saved preview."
              : "Rendering runs locally and only one final export is encoded at a time."}
          </small>
        )}
      </div>
    </section>
  );
}

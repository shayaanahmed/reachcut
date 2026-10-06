import Link from "next/link";

import type { Project } from "../../lib/contracts";
import type { OperationState } from "../projects/use-project-workbench";
import { finalUrl, previewUrl } from "./api";

type Clip = Project["clips"][number];

export function ClipCard({
  projectId,
  clip,
  index,
  bestToPublish,
  approvalPending,
  renderState,
  onApprove,
  onRender,
}: {
  projectId: string;
  clip: Clip;
  index: number;
  bestToPublish: boolean;
  approvalPending: boolean;
  renderState?: OperationState;
  onApprove: (clipId: string, approved: boolean) => Promise<unknown>;
  onRender: (clipId: string) => Promise<unknown>;
}) {
  const slices = clip.plan.source_slices.length
    ? clip.plan.source_slices
    : [clip.plan.source];
  const duration = slices.reduce(
    (total, slice) => total + slice.end_seconds - slice.start_seconds,
    0,
  );
  const studioUrl = `/projects/${projectId}/clips/${clip.id}`;
  const title =
    clip.plan.suggested_title ??
    clip.plan.hook?.text ??
    `Candidate ${index + 1}`;

  return (
    <article className={`clip-row ${clip.approval_status}`}>
      <Link
        className="clip-row-preview"
        href={studioUrl}
        aria-label={`Edit ${title}`}
      >
        {clip.preview_path ? (
          <video
            src={previewUrl(clip.id)}
            muted
            playsInline
            preload="metadata"
          />
        ) : (
          <span aria-hidden="true">▶</span>
        )}
        <span className="clip-duration">{duration.toFixed(0)}s</span>
      </Link>

      <div className="clip-row-copy">
        <div className="clip-row-badges">
          {bestToPublish && (
            <span className="recommendation-badge">Top pick</span>
          )}
          <span>{clip.plan.optimization_goal}</span>
          <span>{clip.plan.content_mode.replaceAll("_", " ")}</span>
          <span
            className={`approval-pill ${clip.approval_status}`}
            aria-live="polite"
          >
            {approvalPending ? "Saving…" : clip.approval_status}
          </span>
        </div>
        <Link href={studioUrl} className="clip-row-title">
          {title}
        </Link>
        <p>{clip.plan.rationale}</p>
        <div className="clip-row-signals">
          <span>
            <strong>{clip.publish_recommendation.score}</strong> potential
          </span>
          <span>
            <strong>{clip.plan.scores.hook}</strong> hook
          </span>
          <span>
            <strong>{clip.plan.scores.payoff}</strong> payoff
          </span>
          <span>
            <strong>{slices.length}</strong> cut{slices.length === 1 ? "" : "s"}
          </span>
        </div>
      </div>

      <div className="clip-row-actions">
        <Link className="studio-link" href={studioUrl}>
          Open studio <span aria-hidden="true">→</span>
        </Link>
        <div>
          <button
            type="button"
            className={
              clip.approval_status === "approved" ? "approve active" : "approve"
            }
            disabled={approvalPending}
            onClick={() => void onApprove(clip.id, true)}
          >
            {clip.approval_status === "approved" ? "Approved ✓" : "Approve"}
          </button>
          <button
            type="button"
            className={
              clip.approval_status === "rejected" ? "reject active" : "reject"
            }
            disabled={approvalPending}
            onClick={() => void onApprove(clip.id, false)}
          >
            {clip.approval_status === "rejected" ? "Rejected" : "Reject"}
          </button>
        </div>
        {clip.approval_status === "approved" && !clip.final_path && (
          <button
            type="button"
            className={`render-button clip-export-action ${renderState ?? "ready"}`}
            aria-live="polite"
            aria-label={
              renderState === "queued"
                ? "Final export queued"
                : renderState === "working"
                  ? "Final export rendering"
                  : "Render final MP4"
            }
            disabled={approvalPending || Boolean(renderState)}
            onClick={() => void onRender(clip.id)}
          >
            <span aria-hidden="true">
              {renderState === "queued"
                ? "⋯"
                : renderState === "working"
                  ? "↻"
                  : "↗"}
            </span>
            <span>
              <strong>
                {renderState === "queued"
                  ? "Export queued"
                  : renderState === "working"
                    ? "Rendering final"
                    : "Render final MP4"}
              </strong>
              <small>
                {renderState ? "Local export in progress" : "Publishing master"}
              </small>
            </span>
          </button>
        )}
        {clip.final_path && (
          <a className="download" href={finalUrl(clip.id)}>
            Download final
          </a>
        )}
      </div>
    </article>
  );
}

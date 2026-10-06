import type { Project, SocialAccount } from "../../lib/contracts";
import type { MetricCreate, PublicationCreate } from "../publishing/api";
import { PublicationTracker } from "../publishing/publication-tracker";
import { finalUrl, previewUrl } from "./api";
import { ClipStyleEditor } from "./clip-style-editor";

type Clip = Project["clips"][number];

export function ClipCard({
  clip,
  accounts,
  index,
  bestToPublish,
  busy,
  onApprove,
  onRender,
  onSaveStyle,
  onTranslate,
  onTrack,
  onUploadAsset,
  onRemoveAsset,
  onPublish,
  onRecordMetrics,
  onRefreshPublication,
  onSyncMetrics,
  onDeletePublication,
}: {
  clip: Clip;
  accounts: SocialAccount[];
  index: number;
  bestToPublish: boolean;
  busy: boolean;
  onApprove: (clipId: string, approved: boolean) => Promise<void>;
  onRender: (clipId: string) => Promise<unknown>;
  onSaveStyle: (clipId: string, form: HTMLFormElement) => Promise<unknown>;
  onTranslate: (
    clipId: string,
    targetLanguage: string,
    mode: "translated" | "bilingual",
  ) => Promise<unknown>;
  onTrack: (clipId: string) => Promise<unknown>;
  onUploadAsset: (clipId: string, form: HTMLFormElement) => Promise<unknown>;
  onRemoveAsset: (clipId: string, assetId: string) => Promise<unknown>;
  onPublish: (clipId: string, data: PublicationCreate) => Promise<unknown>;
  onRecordMetrics: (
    publicationId: string,
    data: MetricCreate,
  ) => Promise<unknown>;
  onDeletePublication: (publicationId: string) => Promise<unknown>;
  onRefreshPublication: (publicationId: string) => Promise<unknown>;
  onSyncMetrics: (publicationId: string) => Promise<unknown>;
}) {
  const sourceSlices =
    clip.plan.source_slices.length > 0
      ? clip.plan.source_slices
      : [clip.plan.source];
  const renderedDuration = sourceSlices.reduce(
    (total, slice) => total + slice.end_seconds - slice.start_seconds,
    0,
  );
  return (
    <div className="clip">
      {clip.preview_path && (
        <video
          className="preview"
          src={previewUrl(clip.id)}
          controls
          preload="metadata"
          aria-label={`Preview ${index + 1}`}
        />
      )}
      <div className="score">{clip.plan.scores.overall}</div>
      <div>
        {bestToPublish && (
          <span className="best-publish-badge">Best to publish</span>
        )}
        <span className="best-publish-badge">
          {clip.plan.optimization_goal === "revenue"
            ? "Revenue version"
            : "Views version"}
        </span>
        <span className="best-publish-badge">
          {clip.plan.content_mode.replace("_", " ")}
        </span>
        <strong>
          {clip.plan.suggested_title ??
            clip.plan.hook?.text ??
            `Candidate ${index + 1}`}
        </strong>
        {clip.plan.hashtags.length > 0 && (
          <p className="hashtags">{clip.plan.hashtags.join(" ")}</p>
        )}
        <p>{clip.plan.rationale}</p>
        <small>
          {clip.plan.source.start_seconds.toFixed(1)}–
          {clip.plan.source.end_seconds.toFixed(1)}s source ·{" "}
          {renderedDuration.toFixed(1)}s render · editorial heuristic
        </small>
        <div className="publish-recommendation">
          <strong>
            Publish potential {clip.publish_recommendation.score}/100 ·{" "}
            {clip.publish_recommendation.confidence} confidence
          </strong>
          <ul>
            {clip.publish_recommendation.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <small>
            Directional estimate from editorial signals; reach and earnings are
            not guaranteed.
          </small>
        </div>
      </div>
      <div className="actions">
        <button
          className="approve"
          onClick={() => void onApprove(clip.id, true)}
        >
          Approve
        </button>
        <button
          className="reject"
          onClick={() => void onApprove(clip.id, false)}
        >
          Reject
        </button>
        {clip.approval_status === "approved" && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() => void onRender(clip.id)}
          >
            Render final
          </button>
        )}
        {clip.final_path && (
          <a className="download" href={finalUrl(clip.id)}>
            Download final
          </a>
        )}
      </div>
      <ClipStyleEditor
        clip={clip}
        busy={busy}
        onSave={onSaveStyle}
        onTranslate={onTranslate}
        onTrack={onTrack}
        onUploadAsset={onUploadAsset}
        onRemoveAsset={onRemoveAsset}
      />
      <PublicationTracker
        clip={clip}
        accounts={accounts}
        busy={busy}
        onPublish={onPublish}
        onRecordMetrics={onRecordMetrics}
        onRefreshPublication={onRefreshPublication}
        onSyncMetrics={onSyncMetrics}
        onDeletePublication={onDeletePublication}
      />
    </div>
  );
}

import type { Project } from "../../lib/contracts";
import { finalUrl, previewUrl } from "./api";
import { ClipStyleEditor } from "./clip-style-editor";

type Clip = Project["clips"][number];

export function ClipCard({
  clip,
  index,
  busy,
  onApprove,
  onRender,
  onSaveStyle,
}: {
  clip: Clip;
  index: number;
  busy: boolean;
  onApprove: (clipId: string, approved: boolean) => Promise<void>;
  onRender: (clipId: string) => Promise<void>;
  onSaveStyle: (clipId: string, form: HTMLFormElement) => Promise<void>;
}) {
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
        <strong>{clip.plan.hook?.text ?? `Candidate ${index + 1}`}</strong>
        <p>{clip.plan.rationale}</p>
        <small>
          {clip.plan.source.start_seconds.toFixed(1)}–
          {clip.plan.source.end_seconds.toFixed(1)}s · editorial heuristic
        </small>
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
      <ClipStyleEditor clip={clip} busy={busy} onSave={onSaveStyle} />
    </div>
  );
}

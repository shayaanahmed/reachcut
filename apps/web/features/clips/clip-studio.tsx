"use client";

import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useProjectWorkbench } from "../projects/use-project-workbench";
import { previewUrl, thumbnailUrl, type ThumbnailTemplate } from "./api";
import {
  ClipStyleEditor,
  studioPreviewFromClip,
  type StudioPreviewState,
} from "./clip-style-editor";
import { FinalExportPanel } from "./final-export-panel";

type PreviewLayer = "caption" | "hook" | "cta";

export function ClipStudio({
  projectId,
  clipId,
}: {
  projectId: string;
  clipId: string;
}) {
  const workbench = useProjectWorkbench(projectId);
  const router = useRouter();
  const project = workbench.projects.find((item) => item.id === projectId);
  const clip = project?.clips.find((item) => item.id === clipId);
  const [preview, setPreview] = useState<StudioPreviewState | null>(null);
  const [previewLayer, setPreviewLayer] = useState<PreviewLayer>("caption");
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const planFingerprint = useMemo(() => {
    if (!clip) return "loading";
    const serialized = JSON.stringify(clip.plan);
    return `${serialized.length}-${serialized.split("").reduce((sum, character) => sum + character.charCodeAt(0), 0)}`;
  }, [clip]);

  if (workbench.loading) return <StudioLoading />;
  if (!project || !clip)
    return (
      <main className="page">
        <div className="empty-state">
          <h1>Clip not found</h1>
          <p>It may have been regenerated or removed.</p>
          <Link className="primary-link" href={`/projects/${projectId}`}>
            Back to project
          </Link>
        </div>
      </main>
    );

  const livePreview =
    hasUnsavedChanges && preview ? preview : studioPreviewFromClip(clip);
  const approvalPending = workbench.isPending(`clip:${clip.id}:approval`);
  const renderState = workbench.operationState(`clip:${clip.id}:render`);
  const saving = workbench.isPending(`clip:${clip.id}:style`);
  const translating = workbench.isPending(`clip:${clip.id}:translate`);
  const tracking = workbench.isPending(`clip:${clip.id}:tracking`);
  const thumbnailGenerating = workbench.isPending(`clip:${clip.id}:thumbnail`);
  const assetBusy = Object.keys(workbench.operations).some((key) =>
    key.startsWith(`clip:${clip.id}:asset`),
  );
  const deleting = workbench.isPending(`clip:${clip.id}:delete`);
  const mutationBusy =
    saving || translating || tracking || assetBusy || deleting;
  const title =
    clip.plan.suggested_title ?? clip.plan.hook?.text ?? "Untitled clip";

  return (
    <main className="studio-page">
      <header className="studio-topbar">
        <div className="studio-breadcrumbs">
          <Link href="/projects">Projects</Link>
          <span>/</span>
          <Link href={`/projects/${project.id}`}>{project.title}</Link>
          <span>/</span>
          <span>Studio</span>
        </div>
        <div className="studio-title-row">
          <div>
            <span className="studio-mode-label">
              CORE WORKSPACE · CLIP STUDIO
            </span>
            <div className="clip-row-badges">
              <span>{clip.plan.optimization_goal}</span>
              <span>{clip.plan.content_mode.replaceAll("_", " ")}</span>
              <span
                className={`approval-pill ${clip.approval_status}`}
                aria-live="polite"
              >
                {clip.approval_status}
              </span>
            </div>
            <h1>{title}</h1>
          </div>
          <div className="studio-header-actions">
            <button
              type="button"
              className="danger-button"
              disabled={mutationBusy || approvalPending || Boolean(renderState)}
              onClick={() => {
                if (
                  window.confirm(
                    `Delete “${title}” completely? Its previews, final render, attached media, and local publishing records will be removed. Published social posts will remain live.`,
                  )
                ) {
                  void workbench.removeClip(clip.id).then((removed) => {
                    if (removed) router.push(`/projects/${project.id}`);
                  });
                }
              }}
            >
              {deleting ? "Deleting…" : "Delete clip"}
            </button>
            <button
              type="button"
              className={
                clip.approval_status === "approved"
                  ? "approve active"
                  : "approve"
              }
              disabled={approvalPending}
              onClick={() => void workbench.approve(clip.id, true)}
            >
              {approvalPending
                ? "Saving…"
                : clip.approval_status === "approved"
                  ? "Approved ✓"
                  : "Approve"}
            </button>
            <button
              type="button"
              className={
                clip.approval_status === "rejected" ? "reject active" : "reject"
              }
              disabled={approvalPending}
              onClick={() => void workbench.approve(clip.id, false)}
            >
              {approvalPending
                ? "Saving…"
                : clip.approval_status === "rejected"
                  ? "Rejected"
                  : "Reject"}
            </button>
            {clip.final_path ? (
              <Link
                className="studio-export-link"
                href={`/projects/${project.id}/clips/${clip.id}/publish`}
              >
                Open publishing →
              </Link>
            ) : (
              <a className="studio-export-link" href="#final-export">
                {renderState === "queued"
                  ? "Export queued"
                  : renderState === "working"
                    ? "Rendering export…"
                    : "Review export"}
              </a>
            )}
          </div>
        </div>
      </header>

      {workbench.error && (
        <p role="alert" className="error studio-error">
          {workbench.error}
        </p>
      )}

      <div className="studio-workspace">
        <aside className="studio-preview-column">
          <div className="studio-preview-heading">
            <div>
              <span className="online-dot" />
              Live design preview
            </div>
            <small>Updates instantly · save to render exact video</small>
          </div>
          <LiveClipPreview
            clipId={clip.id}
            previewPath={clip.preview_path}
            version={planFingerprint}
            state={livePreview}
            layer={previewLayer}
            hasGameplay={clip.plan.secondary_media.some(
              (asset) => asset.kind === "gameplay",
            )}
            hasReaction={clip.plan.secondary_media.some(
              (asset) => asset.kind === "reaction",
            )}
          />
          <div className="preview-layer-tabs" aria-label="Preview overlay">
            {(["caption", "hook", "cta"] as const).map((layer) => (
              <button
                key={layer}
                type="button"
                className={previewLayer === layer ? "active" : ""}
                onClick={() => setPreviewLayer(layer)}
              >
                {layer}
              </button>
            ))}
          </div>
          <div className="preview-quality-note">
            <span>Preview</span>
            <p>
              The canvas mirrors layout and styling immediately. “Save & render
              preview” applies the exact FFmpeg result.
            </p>
          </div>
          <ThumbnailDesigner
            clipId={clip.id}
            ready={clip.thumbnail_ready}
            version={planFingerprint}
            thumbnail={clip.plan.thumbnail}
            generating={thumbnailGenerating}
            onGenerate={workbench.generateThumbnail}
          />
        </aside>

        <ClipStyleEditor
          key={planFingerprint}
          clip={clip}
          saving={saving}
          translating={translating}
          tracking={tracking}
          assetBusy={assetBusy}
          mutationBusy={mutationBusy}
          onSave={workbench.saveStyle}
          onTranslate={workbench.translate}
          onTrack={workbench.analyzeTracking}
          onUploadAsset={workbench.uploadSecondaryMedia}
          onRemoveAsset={workbench.removeSecondaryMedia}
          onPreviewChange={setPreview}
          onDirtyChange={setHasUnsavedChanges}
        />
      </div>

      <FinalExportPanel
        clip={clip}
        publishHref={`/projects/${project.id}/clips/${clip.id}/publish`}
        hasUnsavedChanges={hasUnsavedChanges}
        approvalPending={approvalPending}
        renderState={renderState}
        onApprove={workbench.approve}
        onRender={workbench.render}
      />
    </main>
  );
}

const thumbnailTemplates: Array<{
  value: ThumbnailTemplate;
  label: string;
  description: string;
}> = [
  { value: "speaker", label: "Speaker", description: "Face + bold hook" },
  { value: "question", label: "Question", description: "Centered curiosity" },
  { value: "cinematic", label: "Cinematic", description: "Story-led frame" },
  { value: "minimal", label: "Minimal", description: "Clean brand card" },
];

function ThumbnailDesigner({
  clipId,
  ready,
  version,
  thumbnail,
  generating,
  onGenerate,
}: {
  clipId: string;
  ready: boolean;
  version: string;
  thumbnail: {
    template: ThumbnailTemplate;
    headline: string | null;
    frame_time_seconds: number | null;
  };
  generating: boolean;
  onGenerate: (
    clipId: string,
    data: { template: ThumbnailTemplate; headline?: string },
  ) => Promise<unknown>;
}) {
  const [template, setTemplate] = useState<ThumbnailTemplate>(
    thumbnail.template,
  );
  const [headline, setHeadline] = useState(thumbnail.headline ?? "");

  return (
    <section className="thumbnail-designer" aria-labelledby="thumbnail-title">
      <div className="thumbnail-designer-heading">
        <div>
          <span className="eyebrow">LOCAL AI COVER</span>
          <h2 id="thumbnail-title">Clip thumbnail</h2>
        </div>
        {ready && <span className="thumbnail-ready">Ready</span>}
      </div>
      <div
        className={`thumbnail-preview ${ready ? "ready" : "empty"}`}
        role="img"
        aria-label={ready ? "Generated clip thumbnail" : "Thumbnail preview"}
        style={
          ready
            ? {
                backgroundImage: `url(${thumbnailUrl(clipId)}?v=${encodeURIComponent(version)})`,
              }
            : undefined
        }
      >
        {!ready && (
          <div>
            <strong>Choose a look</strong>
            <small>
              The local vision model will select the strongest frame.
            </small>
          </div>
        )}
        {generating && (
          <div className="thumbnail-generating" role="status">
            <span /> Analyzing frames locally…
          </div>
        )}
      </div>
      <div className="thumbnail-template-grid" aria-label="Thumbnail template">
        {thumbnailTemplates.map((option) => (
          <button
            key={option.value}
            type="button"
            className={template === option.value ? "selected" : ""}
            aria-pressed={template === option.value}
            onClick={() => setTemplate(option.value)}
          >
            <strong>{option.label}</strong>
            <small>{option.description}</small>
          </button>
        ))}
      </div>
      <label>
        Thumbnail headline <small>Optional · AI suggests one if blank</small>
        <input
          value={headline}
          maxLength={80}
          placeholder="Leave blank for a local AI suggestion"
          onChange={(event) => setHeadline(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="thumbnail-generate-action"
        disabled={generating}
        onClick={() =>
          void onGenerate(clipId, {
            template,
            headline: headline.trim() || undefined,
          })
        }
      >
        {generating
          ? "Generating without blocking your edit…"
          : ready
            ? "Regenerate thumbnail"
            : "Generate thumbnail"}
      </button>
      {ready && thumbnail.frame_time_seconds !== null && (
        <small className="thumbnail-frame-note">
          Selected near {thumbnail.frame_time_seconds.toFixed(1)}s · PNG
          1280×720
        </small>
      )}
    </section>
  );
}

function LiveClipPreview({
  clipId,
  previewPath,
  version,
  state,
  layer,
  hasGameplay,
  hasReaction,
}: {
  clipId: string;
  previewPath: string | null;
  version: string;
  state: StudioPreviewState;
  layer: PreviewLayer;
  hasGameplay: boolean;
  hasReaction: boolean;
}) {
  const gameplay = hasGameplay || state.contentMode === "gameplay";
  const style = {
    "--focus-x": `${state.cropFocusX * 100}%`,
    "--focus-y": `${state.cropFocusY * 100}%`,
    "--caption-size": `${Math.max(14, state.fontSize * 0.32)}px`,
    "--caption-color": state.textColor,
    "--caption-highlight": state.highlightColor,
    "--caption-outline": state.outlineColor,
  } as CSSProperties;
  const captionWords = state.captionText.split(/\s+/).slice(0, 7);

  return (
    <div
      className={`studio-phone-stage ${state.frameStyle} ${gameplay ? "gameplay" : ""} ${state.zoomEffect}`}
      style={style}
    >
      {previewPath ? (
        <video
          key={version}
          className="studio-main-video"
          src={`${previewUrl(clipId)}?v=${version}`}
          controls
          playsInline
          preload="metadata"
        />
      ) : (
        <div className="studio-video-placeholder">
          <span>▶</span>
          <small>Preview renders after analysis</small>
        </div>
      )}
      {gameplay && (
        <div className="studio-gameplay-panel">
          <span>GAMEPLAY</span>
          <small>Attached footage</small>
        </div>
      )}
      {hasReaction && <div className="studio-reaction-pip">Reaction</div>}
      {layer === "caption" && state.captionEnabled && (
        <div className={`studio-caption-preview ${state.captionPosition}`}>
          {captionWords.map((word, index) => (
            <span
              className={index === 1 ? "highlight" : ""}
              key={`${word}-${index}`}
            >
              {word}{" "}
            </span>
          ))}
        </div>
      )}
      {layer === "hook" && state.hookRender && (
        <div className="studio-hook-preview">
          {state.hookText || "Opening hook"}
        </div>
      )}
      {layer === "cta" && state.ctaRender && (
        <div className="studio-cta-preview">
          {state.ctaText || "Follow for more"}
        </div>
      )}
      {state.progressBar && (
        <div className="studio-progress-preview">
          <span />
        </div>
      )}
      <div className="studio-safe-zone" aria-hidden="true" />
    </div>
  );
}

function StudioLoading() {
  return (
    <main className="studio-page">
      <div className="studio-loading-shell">
        <div />
        <div>
          <span />
          <span />
          <span />
        </div>
      </div>
    </main>
  );
}

"use client";

import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import Link from "next/link";

import { useProjectWorkbench } from "../projects/use-project-workbench";
import { previewUrl } from "./api";
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
  const assetBusy = Object.keys(workbench.operations).some((key) =>
    key.startsWith(`clip:${clip.id}:asset`),
  );
  const mutationBusy = saving || translating || tracking || assetBusy;
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

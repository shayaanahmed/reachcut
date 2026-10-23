import { useState, type Dispatch, type SetStateAction } from "react";
import Link from "next/link";

import { ClipCard } from "../clips/clip-card";
import { ProjectPerformance } from "../publishing/project-performance";
import type {
  ClipType,
  ClipTypeSuggestion,
  Project,
} from "../../lib/contracts";
import { API_URL } from "../../lib/http";
import { formatBytes } from "../../lib/format";
import { ProjectProgress } from "./project-progress";
import { projectPhase } from "./project-queue";
import type { OperationState } from "./use-project-workbench";

export function ProjectCard({
  project,
  showProcessingControls = true,
  language,
  selectedClipTypes,
  clipTypeSuggestions,
  setLanguages,
  setClipTypes,
  isPending,
  operationState,
  onProcess,
  onStop,
  onRetry,
  onApprove,
  onDeleteClip,
  onRender,
  onRename,
  onDelete,
}: {
  project: Project;
  showProcessingControls?: boolean;
  language: string;
  selectedClipTypes: ClipType[];
  clipTypeSuggestions: ClipTypeSuggestion[];
  setLanguages: Dispatch<SetStateAction<Record<string, string>>>;
  setClipTypes: Dispatch<SetStateAction<Record<string, ClipType[]>>>;
  isPending: (key: string) => boolean;
  operationState: (key: string) => OperationState | undefined;
  onProcess: (id: string, mode?: "clips" | "metadata") => Promise<unknown>;
  onStop?: (id: string) => Promise<unknown>;
  onRetry?: (id: string) => Promise<unknown>;
  onApprove: (clipId: string, approved: boolean) => Promise<unknown>;
  onDeleteClip: (clipId: string) => Promise<unknown>;
  onRender: (clipId: string) => Promise<unknown>;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
}) {
  const [mode, setMode] = useState<"clips" | "metadata">(
    (project.job?.processing_mode === "language"
      ? "metadata"
      : project.job?.processing_mode) ??
      (project.status === "complete" ? "metadata" : "clips"),
  );
  const processing = isPending(`project:${project.id}:process`);
  const retrying = isPending(`project:${project.id}:retry`);
  const pausing = isPending(`project:${project.id}:stop`);
  const active = [
    "queued",
    "downloading",
    "processing",
    "cancel_requested",
  ].includes(project.status);
  const paused = project.status === "cancelled";
  const retryable = paused || project.status === "failed";
  const starting = processing || retrying;
  const pausingRequested = project.status === "cancel_requested";
  const renaming = isPending(`project:${project.id}:rename`);
  const deleting = isPending(`project:${project.id}:delete`);
  const bestClipId = project.clips.reduce<string | null>((bestId, clip) => {
    if (!bestId) return clip.id;
    const currentBest = project.clips.find(
      (candidate) => candidate.id === bestId,
    );
    return !currentBest ||
      clip.publish_recommendation.score >
        currentBest.publish_recommendation.score
      ? clip.id
      : bestId;
  }, null);

  return (
    <article className="project-workspace">
      <div className="project-workspace-header">
        <div>
          <span className={`status ${project.status}`}>
            {paused ? "Paused" : pausingRequested ? "Pausing" : project.status}
          </span>
          <h1>{project.title}</h1>
          <p>
            {project.original_filename}
            {project.duration_seconds
              ? ` · ${Math.round(project.duration_seconds)}s`
              : ""}
            {` · ${formatBytes(project.storage_bytes)} stored`}
          </p>
        </div>
        <div className="project-admin-actions">
          <details>
            <summary>Rename</summary>
            <form
              action={async (data) => {
                await onRename(project.id, String(data.get("title")));
              }}
            >
              <input
                name="title"
                defaultValue={project.title}
                required
                maxLength={200}
                aria-label="Source video name"
              />
              <button disabled={renaming}>
                {renaming ? "Saving…" : "Save"}
              </button>
            </form>
          </details>
          <button
            className="danger-button"
            type="button"
            disabled={
              deleting ||
              [
                "queued",
                "downloading",
                "processing",
                "cancel_requested",
              ].includes(project.status)
            }
            onClick={() => {
              if (
                window.confirm(
                  `Delete “${project.title}” and all of its local files?`,
                )
              )
                void onDelete(project.id);
            }}
          >
            Delete source video
          </button>
        </div>
      </div>
      <section
        className="project-source-panel"
        aria-labelledby="project-source-title"
      >
        <div className="project-source-player">
          <video
            controls
            playsInline
            preload="metadata"
            aria-label="Source video preview"
            src={`${API_URL}/projects/${project.id}/source`}
          />
        </div>
        <div className="project-source-info">
          <span className="eyebrow">ORIGINAL MEDIA</span>
          <h2 id="project-source-title">Source video</h2>
          <p>Preview your original upload before choosing what to create.</p>
          <dl>
            <div>
              <dt>File</dt>
              <dd>{project.original_filename}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>
                {project.duration_seconds
                  ? `${Math.floor(project.duration_seconds / 60)}:${String(Math.floor(project.duration_seconds % 60)).padStart(2, "0")}`
                  : "Available after inspection"}
              </dd>
            </div>
            <div>
              <dt>Storage</dt>
              <dd>{formatBytes(project.storage_bytes)}</dd>
            </div>
          </dl>
          <Link href="/publishing">Open Publishing →</Link>
        </div>
      </section>
      {(showProcessingControls || active || retryable) && (
        <section className="analysis-bar" aria-label="Processing settings">
          <div className="pipeline-control-heading">
            <div>
              <span className="eyebrow">PROCESSING</span>
              <h2>{paused ? "Pipeline paused" : projectPhase(project)}</h2>
              <p aria-live="polite">
                {pausingRequested
                  ? "Waiting for the current operation to stop safely. Completed stages are saved."
                  : active
                    ? "Processing in the background. You can pause and return later."
                    : retryable
                      ? "Resume with your saved settings. Completed stages are reused; interrupted work runs again."
                      : mode === "metadata"
                        ? "Generate a fresh title, description, and hashtags for your videos. Edits and video files are preserved."
                        : "Transcribe your source, generate clips, and write titles, descriptions, and hashtags."}
              </p>
            </div>
            {active ? (
              <button
                type="button"
                className="pipeline-pause"
                disabled={pausing || pausingRequested || !onStop}
                onClick={() => void onStop?.(project.id)}
              >
                {pausing || pausingRequested ? "Pausing…" : "Pause pipeline"}
              </button>
            ) : (
              <button
                type="button"
                className="pipeline-start"
                disabled={starting}
                onClick={() =>
                  void (retryable && onRetry
                    ? onRetry(project.id)
                    : onProcess(project.id, mode))
                }
              >
                {starting
                  ? "Starting…"
                  : paused
                    ? "Resume pipeline"
                    : project.status === "failed"
                      ? "Retry pipeline"
                      : ["review", "complete"].includes(project.status)
                        ? "Run pipeline again"
                        : "Start pipeline"}
              </button>
            )}
          </div>
          {!active && !retryable && (
            <>
              <fieldset className="project-pipeline-modes">
                <legend>What should the pipeline do?</legend>
                <label className={mode === "clips" ? "selected" : ""}>
                  <input
                    type="radio"
                    name={`pipeline-mode-${project.id}`}
                    value="clips"
                    checked={mode === "clips"}
                    onChange={() => setMode("clips")}
                  />
                  <span>
                    <strong>Generate clips</strong>
                    <small>
                      Find highlights, create shorter videos, and write
                      publishing details.
                    </small>
                  </span>
                </label>
                <label className={mode === "metadata" ? "selected" : ""}>
                  <input
                    type="radio"
                    name={`pipeline-mode-${project.id}`}
                    value="metadata"
                    checked={mode === "metadata"}
                    onChange={() => setMode("metadata")}
                  />
                  <span>
                    <strong>Publishing details only</strong>
                    <small>
                      Update titles, descriptions, and hashtags. Keep existing
                      videos, or prepare the full source if there are none.
                    </small>
                  </span>
                </label>
              </fieldset>
              <div className="analysis-controls">
                <label>
                  Spoken language
                  <select
                    value={language}
                    onChange={(event) =>
                      setLanguages((current) => ({
                        ...current,
                        [project.id]: event.target.value,
                      }))
                    }
                  >
                    <option value="">Auto-detect</option>
                    <option value="ur">Urdu (اردو)</option>
                    <option value="en">English</option>
                    <option value="hi">Hindi (हिन्दी)</option>
                    <option value="ar">Arabic (العربية)</option>
                    <option value="de">German</option>
                    <option value="es">Spanish</option>
                    <option value="fr">French</option>
                  </select>
                </label>
                {mode === "clips" && (
                  <fieldset className="clip-type-picker">
                    <legend>Moments to find</legend>
                    <div>
                      {clipTypeOptions.map((option) => (
                        <label key={option.value}>
                          <input
                            type="checkbox"
                            checked={selectedClipTypes.includes(option.value)}
                            onChange={(event) =>
                              setClipTypes((current) => {
                                const selected = current[project.id] ?? [];
                                return {
                                  ...current,
                                  [project.id]: event.target.checked
                                    ? [...selected, option.value]
                                    : selected.filter(
                                        (item) => item !== option.value,
                                      ),
                                };
                              })
                            }
                          />
                          {option.label}
                        </label>
                      ))}
                    </div>
                    <small>Leave all unchecked for automatic discovery.</small>
                  </fieldset>
                )}
              </div>
            </>
          )}
        </section>
      )}
      {(project.stages.length > 0 || project.job) && (
        <ProjectProgress project={project} />
      )}
      <details>
        <summary>Advanced processing and performance</summary>
        {clipTypeSuggestions.length > 0 && (
          <section
            className="clip-direction-panel"
            aria-labelledby="clip-directions"
          >
            <div>
              <span className="eyebrow">TRANSCRIPT SIGNALS</span>
              <h2 id="clip-directions">Possible clip directions</h2>
              <p>ReachCut found these themes after transcribing your video.</p>
            </div>
            <div className="clip-direction-list">
              {clipTypeSuggestions.map((suggestion) => (
                <button
                  type="button"
                  key={suggestion.clip_type}
                  className={
                    selectedClipTypes.includes(suggestion.clip_type)
                      ? "active"
                      : ""
                  }
                  onClick={() =>
                    setClipTypes((current) => ({
                      ...current,
                      [project.id]: selectedClipTypes.includes(
                        suggestion.clip_type,
                      )
                        ? selectedClipTypes.filter(
                            (item) => item !== suggestion.clip_type,
                          )
                        : [...selectedClipTypes, suggestion.clip_type],
                    }))
                  }
                >
                  <strong>{clipTypeLabel(suggestion.clip_type)}</strong>
                  <span>{suggestion.score}% signal</span>
                  <small>{suggestion.reason}</small>
                </button>
              ))}
            </div>
          </section>
        )}
        <ProjectPerformance project={project} />
      </details>
      {project.clips.length > 0 && (
        <section
          className="clip-review-queue"
          aria-labelledby="clip-review-title"
        >
          <div className="clip-review-heading">
            <div>
              <span className="eyebrow">REVIEW QUEUE</span>
              <h2 id="clip-review-title">{project.clips.length} videos</h2>
            </div>
            <p>
              Approve quickly here, or open a clip in Studio for detailed
              editing.
            </p>
          </div>
          <div className="clip-rows">
            {project.clips.map((clip, index) => (
              <ClipCard
                key={clip.id}
                projectId={project.id}
                clip={clip}
                index={index}
                bestToPublish={clip.id === bestClipId}
                approvalPending={isPending(`clip:${clip.id}:approval`)}
                deletionPending={isPending(`clip:${clip.id}:delete`)}
                renderState={operationState(`clip:${clip.id}:render`)}
                onApprove={onApprove}
                onDelete={onDeleteClip}
                onRender={onRender}
              />
            ))}
          </div>
        </section>
      )}
    </article>
  );
}

const clipTypeOptions: { value: ClipType; label: string }[] = [
  { value: "funny", label: "Funny" },
  { value: "advice", label: "Advice" },
  { value: "insight", label: "Insights" },
  { value: "story", label: "Stories" },
  { value: "debate", label: "Debate" },
  { value: "educational", label: "Educational" },
  { value: "emotional", label: "Emotional" },
  { value: "promotional", label: "Promotional" },
];

function clipTypeLabel(value: ClipType) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

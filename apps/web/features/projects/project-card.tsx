import type { Dispatch, SetStateAction } from "react";

import { ClipCard } from "../clips/clip-card";
import { ProjectPerformance } from "../publishing/project-performance";
import type {
  ClipType,
  ClipTypeSuggestion,
  Project,
} from "../../lib/contracts";
import { formatBytes } from "../../lib/format";
import { ProjectProgress } from "./project-progress";
import { projectPhase } from "./project-queue";
import type { OperationState } from "./use-project-workbench";

export function ProjectCard({
  project,
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
  language: string;
  selectedClipTypes: ClipType[];
  clipTypeSuggestions: ClipTypeSuggestion[];
  setLanguages: Dispatch<SetStateAction<Record<string, string>>>;
  setClipTypes: Dispatch<SetStateAction<Record<string, ClipType[]>>>;
  isPending: (key: string) => boolean;
  operationState: (key: string) => OperationState | undefined;
  onProcess: (id: string) => Promise<unknown>;
  onStop?: (id: string) => Promise<unknown>;
  onRetry?: (id: string) => Promise<unknown>;
  onApprove: (clipId: string, approved: boolean) => Promise<unknown>;
  onDeleteClip: (clipId: string) => Promise<unknown>;
  onRender: (clipId: string) => Promise<unknown>;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
}) {
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
                aria-label="Project name"
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
            Delete project
          </button>
        </div>
      </div>
      <section className="analysis-bar" aria-label="Project pipeline">
        <div className="pipeline-control-heading">
          <div>
            <span className="eyebrow">PROJECT PIPELINE</span>
            <h2>{paused ? "Pipeline paused" : projectPhase(project)}</h2>
            <p aria-live="polite">
              {pausingRequested
                ? "Waiting for the current operation to stop safely. Completed stages are saved."
                : active
                  ? "Processing in the background. You can pause and return later."
                  : retryable
                    ? "Resume with your saved settings. Completed stages are reused; interrupted work runs again."
                    : project.status === "review"
                      ? "Your clips are ready below. Run the pipeline again to regenerate clips."
                      : "Choose your settings, then start transcription and highlight selection."}
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
                  : onProcess(project.id))
              }
            >
              {starting
                ? "Starting…"
                : paused
                  ? "Resume pipeline"
                  : project.status === "failed"
                    ? "Retry pipeline"
                    : project.status === "review"
                      ? "Run pipeline again"
                      : "Start pipeline"}
            </button>
          )}
        </div>
        {!active && !retryable && (
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
          </div>
        )}
      </section>
      {(project.stages.length > 0 || project.job) && (
        <ProjectProgress project={project} />
      )}
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
      {project.clips.length > 0 && (
        <section
          className="clip-review-queue"
          aria-labelledby="clip-review-title"
        >
          <div className="clip-review-heading">
            <div>
              <span className="eyebrow">REVIEW QUEUE</span>
              <h2 id="clip-review-title">
                {project.clips.length} generated clips
              </h2>
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

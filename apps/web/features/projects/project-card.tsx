import type { Dispatch, SetStateAction } from "react";

import { ClipCard } from "../clips/clip-card";
import { ProjectPerformance } from "../publishing/project-performance";
import type { Project } from "../../lib/contracts";
import { ProjectProgress } from "./project-progress";
import type { OperationState } from "./use-project-workbench";

export function ProjectCard({
  project,
  language,
  setLanguages,
  isPending,
  operationState,
  onProcess,
  onApprove,
  onRender,
  onRename,
  onDelete,
}: {
  project: Project;
  language: string;
  setLanguages: Dispatch<SetStateAction<Record<string, string>>>;
  isPending: (key: string) => boolean;
  operationState: (key: string) => OperationState | undefined;
  onProcess: (id: string) => Promise<unknown>;
  onApprove: (clipId: string, approved: boolean) => Promise<unknown>;
  onRender: (clipId: string) => Promise<unknown>;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
}) {
  const processing = isPending(`project:${project.id}:process`);
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
          <span className={`status ${project.status}`}>{project.status}</span>
          <h1>{project.title}</h1>
          <p>
            {project.original_filename}
            {project.duration_seconds
              ? ` · ${Math.round(project.duration_seconds)}s`
              : ""}
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
            disabled={deleting || project.status === "processing"}
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
      {["created", "failed", "review"].includes(project.status) && (
        <div className="analysis-bar">
          <div>
            <strong>
              {project.status === "created"
                ? "Ready to analyze"
                : "Run analysis again"}
            </strong>
            <small>Transcription and highlight selection run locally.</small>
          </div>
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
            <button
              className="secondary"
              disabled={processing}
              onClick={() => void onProcess(project.id)}
            >
              {processing
                ? "Starting…"
                : project.status === "created"
                  ? "Analyze"
                  : "Re-analyze"}
            </button>
          </div>
        </div>
      )}
      {project.stages.length > 0 && <ProjectProgress project={project} />}
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
                renderState={operationState(`clip:${clip.id}:render`)}
                onApprove={onApprove}
                onRender={onRender}
              />
            ))}
          </div>
        </section>
      )}
    </article>
  );
}

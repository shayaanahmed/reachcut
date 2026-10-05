import type { Dispatch, SetStateAction } from "react";

import { ClipCard } from "../clips/clip-card";
import type { MetricCreate, PublicationCreate } from "../publishing/api";
import { ProjectPerformance } from "../publishing/project-performance";
import type { Project, SocialAccount } from "../../lib/contracts";
import { ProjectProgress } from "./project-progress";

export function ProjectCard({
  project,
  accounts,
  busy,
  language,
  setLanguages,
  onProcess,
  onApprove,
  onRender,
  onSaveStyle,
  onPublish,
  onRecordMetrics,
  onRefreshPublication,
  onSyncMetrics,
  onDeletePublication,
  onRename,
  onDelete,
}: {
  project: Project;
  accounts: SocialAccount[];
  busy: boolean;
  language: string;
  setLanguages: Dispatch<SetStateAction<Record<string, string>>>;
  onProcess: (id: string) => Promise<unknown>;
  onApprove: (clipId: string, approved: boolean) => Promise<void>;
  onRender: (clipId: string) => Promise<unknown>;
  onSaveStyle: (clipId: string, form: HTMLFormElement) => Promise<unknown>;
  onPublish: (clipId: string, data: PublicationCreate) => Promise<unknown>;
  onRecordMetrics: (
    publicationId: string,
    data: MetricCreate,
  ) => Promise<unknown>;
  onDeletePublication: (publicationId: string) => Promise<unknown>;
  onRefreshPublication: (publicationId: string) => Promise<unknown>;
  onSyncMetrics: (publicationId: string) => Promise<unknown>;
  onRename: (id: string, title: string) => Promise<unknown>;
  onDelete: (id: string) => Promise<unknown>;
}) {
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
              <button disabled={busy}>Save</button>
            </form>
          </details>
          <button
            className="danger-button"
            type="button"
            disabled={busy || project.status === "processing"}
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
              disabled={busy}
              onClick={() => void onProcess(project.id)}
            >
              {project.status === "created" ? "Analyze" : "Re-analyze"}
            </button>
          </div>
        </div>
      )}
      {project.stages.length > 0 && <ProjectProgress project={project} />}
      <ProjectPerformance project={project} />
      {project.clips.length > 0 && (
        <div className="clips">
          {project.clips.map((clip, index) => (
            <ClipCard
              key={clip.id}
              clip={clip}
              accounts={accounts}
              index={index}
              bestToPublish={clip.id === bestClipId}
              busy={busy}
              onApprove={onApprove}
              onRender={onRender}
              onSaveStyle={onSaveStyle}
              onPublish={onPublish}
              onRecordMetrics={onRecordMetrics}
              onRefreshPublication={onRefreshPublication}
              onSyncMetrics={onSyncMetrics}
              onDeletePublication={onDeletePublication}
            />
          ))}
        </div>
      )}
    </article>
  );
}

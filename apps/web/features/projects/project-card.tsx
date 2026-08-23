import type { Dispatch, SetStateAction } from "react";

import { ClipCard } from "../clips/clip-card";
import type { Project } from "../../lib/contracts";
import { ProjectProgress } from "./project-progress";

export function ProjectCard({
  project,
  busy,
  language,
  setLanguages,
  onProcess,
  onApprove,
  onRender,
  onSaveStyle,
}: {
  project: Project;
  busy: boolean;
  language: string;
  setLanguages: Dispatch<SetStateAction<Record<string, string>>>;
  onProcess: (id: string) => Promise<void>;
  onApprove: (clipId: string, approved: boolean) => Promise<void>;
  onRender: (clipId: string) => Promise<void>;
  onSaveStyle: (clipId: string, form: HTMLFormElement) => Promise<void>;
}) {
  return (
    <article className="project">
      <div>
        <span className={`status ${project.status}`}>{project.status}</span>
        <h3>{project.title}</h3>
        <p>
          {project.original_filename}
          {project.duration_seconds
            ? ` · ${Math.round(project.duration_seconds)}s`
            : ""}
        </p>
      </div>
      {["created", "failed", "review"].includes(project.status) && (
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
      )}
      {project.stages.length > 0 && <ProjectProgress project={project} />}
      {project.clips.length > 0 && (
        <div className="clips">
          {project.clips.map((clip, index) => (
            <ClipCard
              key={clip.id}
              clip={clip}
              index={index}
              busy={busy}
              onApprove={onApprove}
              onRender={onRender}
              onSaveStyle={onSaveStyle}
            />
          ))}
        </div>
      )}
    </article>
  );
}

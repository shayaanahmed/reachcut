import type { Dispatch, SetStateAction } from "react";

import type { Project } from "../../lib/contracts";
import { ProjectCard } from "./project-card";

export function ProjectList({
  projects,
  busy,
  languages,
  setLanguages,
  onProcess,
  onApprove,
  onRender,
  onSaveStyle,
}: {
  projects: Project[];
  busy: boolean;
  languages: Record<string, string>;
  setLanguages: Dispatch<SetStateAction<Record<string, string>>>;
  onProcess: (id: string) => Promise<void>;
  onApprove: (clipId: string, approved: boolean) => Promise<void>;
  onRender: (clipId: string) => Promise<void>;
  onSaveStyle: (clipId: string, form: HTMLFormElement) => Promise<void>;
}) {
  return (
    <section aria-labelledby="projects">
      <div className="section-title">
        <h2 id="projects">Projects</h2>
        <span>{projects.length} LOCAL</span>
      </div>
      <div className="projects">
        {projects.length === 0 ? (
          <p className="empty">No media imported yet.</p>
        ) : (
          projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              busy={busy}
              language={languages[project.id] ?? ""}
              setLanguages={setLanguages}
              onProcess={onProcess}
              onApprove={onApprove}
              onRender={onRender}
              onSaveStyle={onSaveStyle}
            />
          ))
        )}
      </div>
    </section>
  );
}

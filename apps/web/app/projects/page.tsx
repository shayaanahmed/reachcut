"use client";

import Link from "next/link";

import { ProjectList } from "../../features/projects/project-list";
import { useProjectWorkbench } from "../../features/projects/use-project-workbench";

export default function ProjectsPage() {
  const workbench = useProjectWorkbench();
  return (
    <main className="page">
      <div className="topbar">
        <div>
          <span className="eyebrow">LIBRARY</span>
          <h1>Projects</h1>
          <p>Manage every source, analysis, and finished clip.</p>
        </div>
        <Link className="primary-link" href="/projects/new">
          ＋ New project
        </Link>
      </div>
      {workbench.error && (
        <p role="alert" className="error">
          {workbench.error}
        </p>
      )}
      <section className="section-block" aria-label="All projects">
        {workbench.loading ? (
          <div className="loading-card">Loading projects…</div>
        ) : (
          <ProjectList
            projects={workbench.projects}
            busy={workbench.busy}
            onDelete={workbench.remove}
          />
        )}
      </section>
    </main>
  );
}

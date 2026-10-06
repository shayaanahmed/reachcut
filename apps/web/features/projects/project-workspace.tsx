"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { ProjectCard } from "./project-card";
import { useProjectWorkbench } from "./use-project-workbench";

export function ProjectWorkspace({ projectId }: { projectId: string }) {
  const workbench = useProjectWorkbench(projectId);
  const router = useRouter();
  const project = workbench.projects.find((item) => item.id === projectId);

  if (workbench.loading)
    return (
      <main className="page">
        <div className="loading-card">Loading project…</div>
      </main>
    );
  if (!project)
    return (
      <main className="page">
        <div className="empty-state">
          <h1>Project not found</h1>
          <p>It may have been removed from this workspace.</p>
          <Link className="primary-link" href="/projects">
            Back to projects
          </Link>
        </div>
      </main>
    );

  return (
    <main className="page">
      <div className="breadcrumbs">
        <Link href="/projects">Projects</Link>
        <span>/</span>
        <span>{project.title}</span>
      </div>
      {workbench.error && (
        <p role="alert" className="error">
          {workbench.error}
        </p>
      )}
      <ProjectCard
        project={project}
        language={workbench.languages[project.id] ?? ""}
        setLanguages={workbench.setLanguages}
        isPending={workbench.isPending}
        operationState={workbench.operationState}
        onProcess={workbench.process}
        onApprove={workbench.approve}
        onRender={workbench.render}
        onRename={workbench.rename}
        onDelete={async (id) => {
          const removed = await workbench.remove(id);
          if (removed) router.push("/projects");
        }}
      />
    </main>
  );
}

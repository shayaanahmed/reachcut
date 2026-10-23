"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { SourceWorkflows } from "./source-workflows";
import { QualityReviewDetails } from "./quality-review";
import { ProjectCard } from "./project-card";
import { useProjectWorkbench } from "./use-project-workbench";

export function ProjectWorkspace({ projectId }: { projectId: string }) {
  const workbench = useProjectWorkbench(projectId);
  const router = useRouter();
  const project = workbench.projects.find((item) => item.id === projectId);

  if (workbench.loading)
    return (
      <main className="page">
        <div className="loading-card">Loading source video…</div>
      </main>
    );
  if (!project)
    return (
      <main className="page">
        <div className="empty-state">
          <h1>Source video not found</h1>
          <p>It may have been removed from this workspace.</p>
          <Link className="primary-link" href="/projects">
            Back to source videos
          </Link>
        </div>
      </main>
    );

  return (
    <main className="page">
      <div className="breadcrumbs">
        <Link href="/projects">Source videos</Link>
        <span>/</span>
        <span>{project.title}</span>
      </div>
      {workbench.error && (
        <p role="alert" className="error">
          {workbench.error}
        </p>
      )}
      {project.status === "review" && (
        <QualityReviewDetails projectId={project.id} />
      )}
      <SourceWorkflows
        project={project}
        onChanged={() => void workbench.reload()}
      />
      <ProjectCard
        showProcessingControls={false}
        project={project}
        language={workbench.languages[project.id] ?? ""}
        selectedClipTypes={workbench.clipTypes[project.id] ?? []}
        clipTypeSuggestions={workbench.clipTypeSuggestions[project.id] ?? []}
        setLanguages={workbench.setLanguages}
        setClipTypes={workbench.setClipTypes}
        isPending={workbench.isPending}
        operationState={workbench.operationState}
        onStop={workbench.stop}
        onRetry={workbench.retry}
        onProcess={workbench.process}
        onApprove={workbench.approve}
        onDeleteClip={workbench.removeClip}
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

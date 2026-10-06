"use client";

import Link from "next/link";

import { finalUrl } from "../clips/api";
import { useProjectWorkbench } from "../projects/use-project-workbench";
import { PublicationTracker } from "./publication-tracker";

export function ClipPublishingWorkspace({
  projectId,
  clipId,
}: {
  projectId: string;
  clipId: string;
}) {
  const workbench = useProjectWorkbench(projectId, { loadAccounts: true });
  const project = workbench.projects.find((item) => item.id === projectId);
  const clip = project?.clips.find((item) => item.id === clipId);

  if (workbench.loading)
    return (
      <main className="page publishing-page">
        <div className="loading-card">Loading publishing workspace…</div>
      </main>
    );

  if (!project || !clip)
    return (
      <main className="page publishing-page">
        <div className="empty-state">
          <h1>Clip not found</h1>
          <p>It may have been regenerated or removed.</p>
          <Link className="primary-link" href={`/projects/${projectId}`}>
            Back to project
          </Link>
        </div>
      </main>
    );

  const title =
    clip.plan.suggested_title ?? clip.plan.hook?.text ?? "Untitled clip";
  const studioHref = `/projects/${project.id}/clips/${clip.id}`;

  return (
    <main className="page publishing-page">
      <div className="breadcrumbs">
        <Link href="/projects">Projects</Link>
        <span>/</span>
        <Link href={`/projects/${project.id}`}>{project.title}</Link>
        <span>/</span>
        <Link href={studioHref}>Studio</Link>
        <span>/</span>
        <span>Publishing</span>
      </div>

      <header className="publishing-page-header">
        <div>
          <span className="eyebrow">DISTRIBUTION WORKSPACE</span>
          <h1>Publish your finished clip</h1>
          <p>{title}</p>
        </div>
        <div className="publishing-page-actions">
          <Link href={studioHref}>← Back to Studio</Link>
          {clip.final_path && (
            <a href={finalUrl(clip.id)}>Download final MP4</a>
          )}
        </div>
      </header>

      <section className="publishing-clip-summary" aria-label="Clip readiness">
        <div>
          <span className="publishing-summary-icon" aria-hidden="true">
            {clip.final_path ? "✓" : "!"}
          </span>
          <div>
            <strong>
              {clip.final_path
                ? "Publishing master ready"
                : "Final export required"}
            </strong>
            <small>
              {clip.final_path
                ? "Full-quality vertical MP4"
                : "Return to Studio to approve and render this clip"}
            </small>
          </div>
        </div>
        <span className={`approval-pill ${clip.approval_status}`}>
          {clip.approval_status}
        </span>
      </section>

      {workbench.error && (
        <p role="alert" className="error">
          {workbench.error}
        </p>
      )}

      <div className="publishing-page-workspace">
        <PublicationTracker
          clip={clip}
          accounts={workbench.accounts}
          isPending={workbench.isPending}
          onPublish={workbench.publish}
          onRecordMetrics={workbench.recordMetrics}
          onRefreshPublication={workbench.refreshPublishedPost}
          onSyncMetrics={workbench.syncPublishedMetrics}
          onDeletePublication={workbench.removePublication}
        />
      </div>
    </main>
  );
}

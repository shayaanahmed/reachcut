"use client";

import Link from "next/link";
import { ActionLink } from "../../components/action-link";
import { useCallback, useEffect, useState } from "react";
import { ProjectProgress } from "../projects/project-progress";
import { GrowthPanel } from "./growth-panel";
import { loadPublishingCopy, type PlatformCopy } from "./growth-api";

import { finalUrl } from "../clips/api";
import { useProjectWorkbench } from "../projects/use-project-workbench";
import { PublicationTracker } from "./publication-tracker";

export function ClipPublishingWorkspace({
  projectId,
  clipId,
  preferredAccountIds = [],
}: {
  projectId: string;
  clipId: string;
  preferredAccountIds?: string[];
}) {
  const [growthSelection, setGrowthSelection] = useState<{
    clipId: string;
    copy: PlatformCopy[];
  } | null>(null);
  const growthCopy =
    growthSelection?.clipId === clipId ? growthSelection.copy : [];
  const setGrowthCopy = useCallback(
    (copy: PlatformCopy[]) => setGrowthSelection({ clipId, copy }),
    [clipId],
  );
  const workbench = useProjectWorkbench(projectId, { loadAccounts: true });
  const project = workbench.projects.find((item) => item.id === projectId);
  const clip = project?.clips.find((item) => item.id === clipId);
  const [draftNotice, setDraftNotice] = useState("");
  const [draftError, setDraftError] = useState("");
  const [draftReload, setDraftReload] = useState(0);
  const [loadedDraftRevision, setLoadedDraftRevision] = useState("");
  const draftRevision = `${project?.status}:${clip?.plan.suggested_title}:${clip?.plan.suggested_description}:${clip?.plan.hashtags.join(",")}`;
  useEffect(() => {
    let active = true;
    loadPublishingCopy(clipId)
      .then((result) => {
        if (active) {
          setGrowthSelection({ clipId, copy: result.packages });
          setDraftNotice(result.hashtag_notice ?? "");
          setDraftError("");
          setLoadedDraftRevision(draftRevision);
        }
      })
      .catch((error) => {
        if (active)
          setDraftError(
            error instanceof Error
              ? error.message
              : "Could not load latest draft",
          );
      });
    return () => {
      active = false;
    };
  }, [clipId, draftRevision, draftReload]);

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
  const preparing = [
    "queued",
    "downloading",
    "processing",
    "cancel_requested",
  ].includes(project.status);

  return (
    <main className="page publishing-page">
      <div className="breadcrumbs">
        <Link href="/projects">Source videos</Link>
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
          <ActionLink href={studioHref} icon="←">
            Back to Studio
          </ActionLink>
          <ActionLink href={`/publishing/posts?clip=${clip.id}`} icon="↗">
            Manage social posts
          </ActionLink>
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
                ? "Full-quality MP4"
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

      {(preparing || project.status === "failed") && (
        <ProjectProgress project={project} />
      )}
      <GrowthPanel
        autoApply={false}
        key={clip.id}
        refreshKey={JSON.stringify({
          status: project.status,
          title: clip.plan.suggested_title,
          description: clip.plan.suggested_description,
          stages: project.stages.map((stage) => [
            stage.name,
            stage.status,
            stage.finished_at,
          ]),
          metrics: clip.publications.flatMap((p) =>
            p.metric_snapshots.map((m) => m.id),
          ),
        })}
        clipId={clip.id}
        accounts={workbench.accounts}
        onApply={setGrowthCopy}
      />
      {draftError && (
        <p role="alert">
          {draftError}{" "}
          <button onClick={() => setDraftReload((value) => value + 1)}>
            Retry latest draft
          </button>
        </p>
      )}
      {draftNotice && <p role="status">{draftNotice}</p>}
      {growthCopy.length > 0 && (
        <p role="status">
          AI publishing copy is active below. Edit it under Advanced audience,
          evidence & publishing copy if needed.
        </p>
      )}
      <div className="publishing-page-workspace">
        <PublicationTracker
          preparing={
            preparing || loadedDraftRevision !== draftRevision || !!draftError
          }
          preparationMessage={
            draftError
              ? "Latest draft unavailable — use Retry latest draft above"
              : preparing
                ? "Project pipeline is preparing publishing copy…"
                : "Loading latest publishing draft…"
          }
          growthCopy={growthCopy}
          preferredAccountIds={preferredAccountIds}
          clip={clip}
          accounts={workbench.accounts}
          groups={workbench.groups}
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

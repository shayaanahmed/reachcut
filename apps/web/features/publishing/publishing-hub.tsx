"use client";
import { ActionLink } from "../../components/action-link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useProjectWorkbench } from "../projects/use-project-workbench";
import { BulkClipActions } from "./bulk-clip-actions";
import { PublishingVideoUpload } from "./video-upload";

export function PublishingHub() {
  const router = useRouter();
  const workbench = useProjectWorkbench(undefined, { loadAccounts: true });
  const [projectId, setProjectId] = useState("");
  const [query, setQuery] = useState("");
  const projects = workbench.projects.filter((p) => p.clips.length > 0);
  const project = projects.find((p) => p.id === projectId) ?? projects[0];
  const clips = workbench.projects.flatMap((p) => p.clips);
  const posts = clips.flatMap((c) => c.publications);
  const activePosts = posts.filter((p) =>
    ["queued", "processing"].includes(p.status),
  );
  return (
    <main className="page distribution-page">
      <header className="topbar">
        <div>
          <span className="eyebrow">DISTRIBUTION</span>
          <h1>Publishing</h1>
          <p>Review clips, choose channels, and publish from one workspace.</p>
        </div>
        <div className="inline-actions">
          <ActionLink href="/studio" icon="✂">
            Upload & edit in Studio
          </ActionLink>
          <ActionLink href="/settings/accounts" icon="⚙">
            Accounts & groups
          </ActionLink>
          <ActionLink href="/insights" icon="▥">
            View insights
          </ActionLink>
        </div>
      </header>
      <nav className="workspace-switcher" aria-label="Publishing views">
        <span aria-current="page">Publish clips</span>
        <ActionLink
          href="/publishing/posts"
          icon="⚙"
          description="Edit existing posts & manage deletions"
        >
          Manage social posts
        </ActionLink>
        <span className="workspace-counts">
          {posts.filter((p) => p.status === "published").length} published ·{" "}
          {activePosts.length} in progress
        </span>
      </nav>
      {workbench.error && (
        <p className="error" role="alert">
          {workbench.error}
        </p>
      )}
      <details className="upload-disclosure">
        <summary>
          <span aria-hidden="true">＋</span> Upload a finished video{" "}
          <small>Skip clipping and prepare a publishing master</small>
        </summary>
        <PublishingVideoUpload
          busy={workbench.isPending("project:publishing-upload")}
          onUpload={workbench.uploadForPublishing}
          onCreated={(created) => {
            router.push(
              `/projects/${created.id}/clips/${created.clips[0].id}/publish`,
            );
          }}
        />
      </details>
      {workbench.loading ? (
        <p className="loading-card">Loading publishing workspace…</p>
      ) : !projects.length ? (
        <div className="empty-state">
          <h2>No clips to publish yet</h2>
          <p>
            Upload a finished video above, or create a project to generate
            clips.
          </p>
          <ActionLink href="/projects/new" icon="＋">
            Clip a video
          </ActionLink>
        </div>
      ) : (
        <>
          <section className="publishing-project-picker">
            <label>
              Find a project
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search project names"
              />
            </label>
            <label>
              Project
              <select
                aria-label="Publishing project"
                value={project?.id ?? ""}
                onChange={(e) => setProjectId(e.target.value)}
              >
                {projects
                  .filter(
                    (p) =>
                      p.id === project?.id ||
                      p.title.toLowerCase().includes(query.toLowerCase()),
                  )
                  .map((p) => (
                    <option value={p.id} key={p.id}>
                      {p.title} · {p.clips.length} clips
                    </option>
                  ))}
              </select>
            </label>
          </section>
          {project && (
            <>
              <BulkClipActions
                key={project.id}
                project={project}
                accounts={workbench.accounts}
                groups={workbench.groups}
                pending={workbench.isPending(`project:${project.id}:bulk`)}
                onApprove={workbench.bulkApprove}
                onRender={workbench.render}
                onPublish={workbench.bulkPublish}
              />
              <div className="publishing-footer">
                <p>
                  Already posted this clip? Update its existing destinations
                  from the social post board.
                </p>
                <ActionLink href="/publishing/posts" icon="⚙">
                  Manage existing posts
                </ActionLink>
              </div>
            </>
          )}
        </>
      )}
    </main>
  );
}

"use client";
import Link from "next/link";
import { useState } from "react";
import { useProjectWorkbench } from "../projects/use-project-workbench";
import { BulkClipActions } from "./bulk-clip-actions";

export function PublishingHub() {
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
          <Link href="/settings/accounts">Accounts & groups</Link>
          <Link href="/insights">View insights →</Link>
        </div>
      </header>
      <div className="stats-grid">
        <article>
          <span>Ready to publish</span>
          <strong>
            {
              clips.filter(
                (c) => c.approval_status === "approved" && c.final_path,
              ).length
            }
          </strong>
        </article>
        <article>
          <span>In progress</span>
          <strong>{activePosts.length}</strong>
        </article>
        <article>
          <span>Published posts</span>
          <strong>
            {posts.filter((p) => p.status === "published").length}
          </strong>
        </article>
        <article>
          <span>Failed posts</span>
          <strong>{posts.filter((p) => p.status === "failed").length}</strong>
        </article>
      </div>
      {workbench.error && (
        <p className="error" role="alert">
          {workbench.error}
        </p>
      )}
      {workbench.loading ? (
        <p className="loading-card">Loading publishing workspace…</p>
      ) : !projects.length ? (
        <div className="empty-state">
          <h2>No clips to publish yet</h2>
          <p>Create a project and generate clips to get started.</p>
          <Link href="/projects/new">Create project →</Link>
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
              <section className="section-block">
                <h2>Publishing activity</h2>
                <p>
                  Current status for this project. Open a post to review details
                  or retry a failure.
                </p>
                <div className="distribution-posts">
                  {project.clips.flatMap((clip) =>
                    clip.publications.map((post) => (
                      <article key={post.id}>
                        <span className={`status ${post.status}`}>
                          {post.status}
                        </span>
                        <div>
                          <strong>{post.title}</strong>
                          <small>
                            {post.account_label} · {post.platform}
                          </small>
                          {post.error && <p className="error">{post.error}</p>}
                        </div>
                        <Link
                          href={`/projects/${project.id}/clips/${clip.id}/publish`}
                        >
                          Open publishing →
                        </Link>
                        {post.post_url && (
                          <a
                            href={post.post_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            View post ↗
                          </a>
                        )}
                      </article>
                    )),
                  )}
                  {!project.clips.some((c) => c.publications.length) && (
                    <p>No posts yet. Select clips and destinations above.</p>
                  )}
                </div>
              </section>
            </>
          )}
        </>
      )}
    </main>
  );
}

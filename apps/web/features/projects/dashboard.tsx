import Link from "next/link";

import type { Project } from "../../lib/contracts";
import { ProjectList } from "./project-list";
import type { useProjectWorkbench } from "./use-project-workbench";

type Workbench = ReturnType<typeof useProjectWorkbench>;

export function summarizeWorkspace(projects: Project[]) {
  let views = 0;
  let engagements = 0;
  let published = 0;
  let exported = 0;

  for (const project of projects) {
    for (const clip of project.clips) {
      if (clip.final_path) exported += 1;
      for (const publication of clip.publications) {
        if (publication.status === "published") published += 1;
        const metrics = publication.metric_snapshots.at(-1);
        if (!metrics) continue;
        views += metrics.views;
        engagements += metrics.likes + metrics.comments + metrics.shares;
      }
    }
  }

  return {
    projects: projects.length,
    views,
    published,
    exported,
    engagementRate: views ? (engagements / views) * 100 : 0,
    attention: projects.filter((project) =>
      ["review", "failed"].includes(project.status),
    ).length,
  };
}

export function Dashboard({ workbench }: { workbench: Workbench }) {
  const summary = summarizeWorkspace(workbench.projects);
  const reviewProjects = workbench.projects.filter(
    (project) => project.status === "review",
  );
  const processingProjects = workbench.projects.filter(
    (project) => project.status === "processing",
  );
  const failedProjects = workbench.projects.filter(
    (project) => project.status === "failed",
  );
  const pendingClips = workbench.projects.flatMap((project) =>
    project.clips
      .filter((clip) => clip.approval_status === "pending")
      .map((clip) => ({ project, clip })),
  );
  const readyToRender = workbench.projects.flatMap((project) =>
    project.clips.filter(
      (clip) => clip.approval_status === "approved" && !clip.final_path,
    ),
  ).length;
  const revenue = workbench.projects.reduce(
    (total, project) =>
      total +
      project.clips.reduce(
        (clipTotal, clip) =>
          clipTotal +
          clip.publications.reduce(
            (publicationTotal, publication) =>
              publicationTotal +
              (publication.metric_snapshots.at(-1)?.revenue ?? 0),
            0,
          ),
        0,
      ),
    0,
  );

  return (
    <main className="page dashboard-page">
      <div className="topbar dashboard-topbar">
        <div>
          <span className="eyebrow">TODAY</span>
          <h1>Content command center</h1>
          <p>
            Move ideas from source to published clip, then learn from what
            performs.
          </p>
        </div>
        <Link className="primary-link" href="/projects/new">
          ＋ New project
        </Link>
      </div>
      <section
        className="stats-grid dashboard-stats"
        aria-label="Workspace summary"
      >
        <article className="stat-primary">
          <span>Total views</span>
          <strong>{summary.views.toLocaleString()}</strong>
          <small>latest snapshot from every published post</small>
        </article>
        <article>
          <span>Awaiting review</span>
          <strong>{pendingClips.length.toLocaleString()}</strong>
          <small>across {reviewProjects.length} projects</small>
        </article>
        <article>
          <span>Ready to render</span>
          <strong>{readyToRender.toLocaleString()}</strong>
          <small>{summary.exported} final exports completed</small>
        </article>
        <article>
          <span>Tracked revenue</span>
          <strong>€{revenue.toFixed(2)}</strong>
          <small>{summary.engagementRate.toFixed(1)}% engagement rate</small>
        </article>
      </section>
      <section
        className="dashboard-focus"
        aria-labelledby="next-actions-heading"
      >
        <div className="dashboard-focus-heading">
          <div>
            <span className="eyebrow">NEXT ACTIONS</span>
            <h2 id="next-actions-heading">Keep production moving</h2>
          </div>
          <small>
            {processingProjects.length
              ? `${processingProjects.length} processing now`
              : "Local pipeline is available"}
          </small>
        </div>
        <div className="dashboard-focus-grid">
          <article className={pendingClips.length ? "priority" : ""}>
            <span className="focus-icon">✓</span>
            <div>
              <strong>Review candidates</strong>
              <p>
                {pendingClips.length
                  ? `${pendingClips.length} clips need a decision.`
                  : "Your review queue is clear."}
              </p>
            </div>
            <Link
              href={
                pendingClips[0]
                  ? `/projects/${pendingClips[0].project.id}`
                  : "/projects"
              }
            >
              {pendingClips.length ? "Start review" : "View library"} →
            </Link>
          </article>
          <article className={readyToRender ? "priority" : ""}>
            <span className="focus-icon">↗</span>
            <div>
              <strong>Finish approved clips</strong>
              <p>
                {readyToRender
                  ? `${readyToRender} approved clips are waiting for final render.`
                  : "No render backlog right now."}
              </p>
            </div>
            <Link href="/projects">Open projects →</Link>
          </article>
          <article className={failedProjects.length ? "warning" : ""}>
            <span className="focus-icon">!</span>
            <div>
              <strong>Pipeline health</strong>
              <p>
                {failedProjects.length
                  ? `${failedProjects.length} projects need attention.`
                  : `${processingProjects.length} active · no failures.`}
              </p>
            </div>
            <Link href="/projects">Inspect pipeline →</Link>
          </article>
        </div>
      </section>
      <section className="dashboard-actions" aria-label="Quick actions">
        <div>
          <strong>What do you want to make next?</strong>
          <small>Start with your own media or explore current topics.</small>
        </div>
        <Link href="/projects/new">Import media</Link>
        <Link href="/discover">Explore topics</Link>
      </section>
      {workbench.error && (
        <p role="alert" className="error">
          {workbench.error}
        </p>
      )}
      <section className="section-block" aria-labelledby="recent-projects">
        <div className="section-heading">
          <div>
            <span className="eyebrow">PICK UP WHERE YOU LEFT OFF</span>
            <h2 id="recent-projects">Recent projects</h2>
          </div>
          <Link href="/projects">See all projects →</Link>
        </div>
        {workbench.loading ? (
          <div className="loading-card">Loading projects…</div>
        ) : (
          <ProjectList
            projects={workbench.projects.slice(0, 4)}
            isPending={workbench.isPending}
            onDelete={workbench.remove}
            compact
          />
        )}
      </section>
    </main>
  );
}

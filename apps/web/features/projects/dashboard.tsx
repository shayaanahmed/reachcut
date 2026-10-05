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

  return (
    <main className="page dashboard-page">
      <div className="topbar dashboard-topbar">
        <div>
          <span className="eyebrow">OVERVIEW</span>
          <h1>Your content workspace</h1>
          <p>See what is performing and continue the work that matters.</p>
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
          <span>Published posts</span>
          <strong>{summary.published.toLocaleString()}</strong>
          <small>{summary.exported} clips ready to share</small>
        </article>
        <article>
          <span>Engagement rate</span>
          <strong>{summary.engagementRate.toFixed(1)}%</strong>
          <small>likes, comments, and shares per view</small>
        </article>
        <article>
          <span>Projects</span>
          <strong>{summary.projects.toLocaleString()}</strong>
          <small>
            {summary.attention
              ? `${summary.attention} need your attention`
              : "everything is up to date"}
          </small>
        </article>
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
            busy={workbench.busy}
            onDelete={workbench.remove}
            compact
          />
        )}
      </section>
    </main>
  );
}

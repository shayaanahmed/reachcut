import { ActionLink } from "../../components/action-link";

import { insightPosts, summarizeInsights } from "../publishing/insight-data";
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
        if (publication.status !== "published") continue;
        published += 1;
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
  const processingProjects = workbench.projects.filter((project) =>
    ["queued", "downloading", "processing", "cancel_requested"].includes(
      project.status,
    ),
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
  const revenue = summarizeInsights(insightPosts(workbench.projects)).revenue;
  const revenueLabel =
    Object.entries(revenue)
      .map(([currency, value]) =>
        new Intl.NumberFormat("en", { style: "currency", currency }).format(
          value,
        ),
      )
      .join(" · ") || "€0.00";

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
        <div className="inline-actions">
          <ActionLink href="/publishing" icon="↗">
            Publish clips
          </ActionLink>
          <ActionLink href="/insights" icon="▥">
            View insights
          </ActionLink>
        </div>
        <ActionLink primary href="/projects/new" icon="＋">
          Clip a video
        </ActionLink>
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
          <small>across {reviewProjects.length} source videos</small>
        </article>
        <article>
          <span>Ready to render</span>
          <strong>{readyToRender.toLocaleString()}</strong>
          <small>{summary.exported} final exports completed</small>
        </article>
        <article>
          <span>Tracked revenue</span>
          <strong>{revenueLabel}</strong>
          <small>{summary.engagementRate.toFixed(1)}% engagement rate</small>
        </article>
      </section>
      {(failedProjects.length > 0 || pendingClips.length > 0) && (
        <section className="dashboard-attention" aria-label="Needs attention">
          <div>
            <span className="eyebrow">NEXT UP</span>
            <h2>Ready for your attention</h2>
            <p>
              {processingProjects.length
                ? `${processingProjects.length} projects are processing in the background.`
                : "Pick up the next useful action."}
            </p>
          </div>
          <div className="inline-actions">
            {pendingClips[0] && (
              <ActionLink
                href={`/projects/${pendingClips[0].project.id}`}
                icon="✓"
                description={`${pendingClips.length} clips ready for a decision`}
              >
                Review clips
              </ActionLink>
            )}
            {failedProjects[0] && (
              <ActionLink
                href={`/projects/${failedProjects[0].id}`}
                icon="!"
                description={`${failedProjects.length} projects need a retry`}
              >
                Resolve pipeline issues
              </ActionLink>
            )}
          </div>
        </section>
      )}
      <section className="dashboard-actions" aria-label="Quick actions">
        <div>
          <strong>What do you want to make next?</strong>
          <small>
            Start with your own media or schedule a publishing flow.
          </small>
        </div>
        <ActionLink href="/projects/new" icon="＋">
          Import media
        </ActionLink>
        <ActionLink href="/automations" icon="↻">
          Build automation
        </ActionLink>
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
            <h2 id="recent-projects">Recent source videos</h2>
          </div>
          <ActionLink href="/projects" icon="▤">
            All source videos
          </ActionLink>
        </div>
        {workbench.loading ? (
          <div className="loading-card">Loading source videos…</div>
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

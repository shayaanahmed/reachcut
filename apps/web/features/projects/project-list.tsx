"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import type { Project } from "../../lib/contracts";

type ProjectFilter = "all" | "active" | "review" | "complete";
type ProjectSort = "recent" | "attention" | "performance";
type ProjectView = "grid" | "list";

function latestProjectViews(project: Project) {
  return project.clips.reduce(
    (total, clip) =>
      total +
      clip.publications.reduce(
        (publicationTotal, publication) =>
          publicationTotal + (publication.metric_snapshots.at(-1)?.views ?? 0),
        0,
      ),
    0,
  );
}

function projectProgress(project: Project) {
  if (project.status === "created") return 8;
  if (project.status === "processing") {
    if (project.stages.length === 0) return 24;
    return Math.max(
      12,
      Math.round(
        (project.stages.reduce((sum, stage) => sum + stage.progress, 0) /
          project.stages.length) *
          100,
      ),
    );
  }
  if (project.status === "failed") return 35;
  if (project.status === "review") return 78;
  return 100;
}

function matchesFilter(project: Project, filter: ProjectFilter) {
  if (filter === "active")
    return ["created", "processing", "failed"].includes(project.status);
  if (filter === "review") return project.status === "review";
  if (filter === "complete")
    return project.clips.some((clip) => Boolean(clip.final_path));
  return true;
}

function nextAction(project: Project) {
  if (project.status === "created") return "Run analysis";
  if (project.status === "processing") return "Processing locally";
  if (project.status === "failed") return "Resolve failed stage";
  const pending = project.clips.filter(
    (clip) => clip.approval_status === "pending",
  ).length;
  if (pending) return `Review ${pending} clip${pending === 1 ? "" : "s"}`;
  const approved = project.clips.filter(
    (clip) => clip.approval_status === "approved" && !clip.final_path,
  ).length;
  if (approved) return `Render ${approved} approved`;
  return "View performance";
}

export function ProjectList({
  projects,
  isPending,
  onDelete,
  compact = false,
}: {
  projects: Project[];
  isPending: (key: string) => boolean;
  onDelete: (id: string) => Promise<unknown>;
  compact?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ProjectFilter>("all");
  const [sort, setSort] = useState<ProjectSort>("recent");
  const [view, setView] = useState<ProjectView>("grid");
  const visibleProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const matching = projects.filter(
      (project) =>
        matchesFilter(project, filter) &&
        (!normalizedQuery ||
          project.title.toLocaleLowerCase().includes(normalizedQuery) ||
          project.original_filename
            .toLocaleLowerCase()
            .includes(normalizedQuery)),
    );
    return matching.toSorted((left, right) => {
      if (sort === "performance")
        return latestProjectViews(right) - latestProjectViews(left);
      if (sort === "attention") {
        const priority = (project: Project) =>
          project.status === "failed"
            ? 3
            : project.status === "review"
              ? 2
              : project.status === "created"
                ? 1
                : 0;
        return priority(right) - priority(left);
      }
      return (
        new Date(right.created_at).getTime() -
        new Date(left.created_at).getTime()
      );
    });
  }, [filter, projects, query, sort]);

  if (projects.length === 0) {
    return (
      <div className="empty-state">
        <span className="empty-icon" aria-hidden="true">
          ＋
        </span>
        <h3>No projects yet</h3>
        <p>Import a video to begin finding and editing standout moments.</p>
        <Link className="primary-link" href="/projects/new">
          Create your first project
        </Link>
      </div>
    );
  }

  return (
    <div className="project-browser">
      {!compact && (
        <div className="project-browser-tools">
          <label className="project-search">
            <span aria-hidden="true">⌕</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search projects"
              aria-label="Search projects"
            />
          </label>
          <div className="project-filters" aria-label="Filter projects">
            {(["all", "active", "review", "complete"] as const).map(
              (option) => (
                <button
                  key={option}
                  type="button"
                  className={filter === option ? "active" : ""}
                  aria-pressed={filter === option}
                  onClick={() => setFilter(option)}
                >
                  {option}
                </button>
              ),
            )}
          </div>
          <div className="project-view-tools">
            <select
              value={sort}
              onChange={(event) => setSort(event.target.value as ProjectSort)}
              aria-label="Sort projects"
            >
              <option value="recent">Most recent</option>
              <option value="attention">Needs attention</option>
              <option value="performance">Best performance</option>
            </select>
            <div aria-label="Project view" className="view-switcher">
              <button
                type="button"
                aria-label="Grid view"
                aria-pressed={view === "grid"}
                className={view === "grid" ? "active" : ""}
                onClick={() => setView("grid")}
              >
                ▦
              </button>
              <button
                type="button"
                aria-label="List view"
                aria-pressed={view === "list"}
                className={view === "list" ? "active" : ""}
                onClick={() => setView("list")}
              >
                ☰
              </button>
            </div>
          </div>
        </div>
      )}
      {visibleProjects.length === 0 ? (
        <div className="empty-state compact">
          <h3>No matching projects</h3>
          <p>Try a different search or filter.</p>
        </div>
      ) : (
        <div
          className={`project-grid ${compact ? "compact" : ""} ${!compact && view === "list" ? "list-view" : ""}`}
        >
          {visibleProjects.map((project, index) => {
            const views = latestProjectViews(project);
            const progress = projectProgress(project);
            return (
              <article className="project-tile" key={project.id}>
                <Link
                  className="project-tile-main"
                  href={`/projects/${project.id}`}
                  aria-label={`Open ${project.title}`}
                >
                  <div className={`project-cover cover-${index % 4}`}>
                    <span className="project-cover-icon" aria-hidden="true">
                      ▶
                    </span>
                    <span className="project-cover-label">
                      {nextAction(project)}
                    </span>
                    <strong>{project.clips.length}</strong>
                    <small>clips</small>
                  </div>
                  <div className="project-tile-body">
                    <div className="project-tile-heading">
                      <span className={`status ${project.status}`}>
                        {project.status}
                      </span>
                      <time dateTime={project.created_at}>
                        {new Intl.DateTimeFormat("en", {
                          month: "short",
                          day: "numeric",
                        }).format(new Date(project.created_at))}
                      </time>
                    </div>
                    <h3>{project.title}</h3>
                    <p>{project.original_filename}</p>
                    <div className="project-tile-stats">
                      <span>
                        <strong>{views.toLocaleString()}</strong> views
                      </span>
                      <span>
                        <strong>
                          {
                            project.clips.filter((clip) => clip.final_path)
                              .length
                          }
                        </strong>{" "}
                        exported
                      </span>
                      <span>
                        <strong>
                          {
                            project.clips.filter(
                              (clip) => clip.approval_status === "approved",
                            ).length
                          }
                        </strong>{" "}
                        approved
                      </span>
                    </div>
                    <div className="project-next-action">
                      <span>{nextAction(project)}</span>
                      <strong>Open →</strong>
                    </div>
                    <div className="project-completion">
                      <span style={{ width: `${progress}%` }} />
                    </div>
                  </div>
                </Link>
                <button
                  className="project-delete"
                  type="button"
                  disabled={
                    isPending(`project:${project.id}:delete`) ||
                    project.status === "processing"
                  }
                  aria-label={`Delete ${project.title}`}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Delete “${project.title}” and all of its local files?`,
                      )
                    ) {
                      void onDelete(project.id);
                    }
                  }}
                >
                  {isPending(`project:${project.id}:delete`) ? "…" : "×"}
                </button>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

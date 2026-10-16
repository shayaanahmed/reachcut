import Link from "next/link";

import type { Project } from "../../lib/contracts";

export function projectPhase(project: Project): string {
  if (project.status === "queued") return "Waiting to start";
  if (project.status === "downloading") return "Downloading video";
  if (project.status === "cancel_requested")
    return "Pausing after the current operation";
  if (project.status === "cancelled") return "Paused";
  if (project.status === "failed") return "Needs attention";
  if (project.status === "review") return "Ready for review";
  const stage = project.stages.find((item) => item.status === "running");
  const labels: Record<string, string> = {
    probe: "Preparing media",
    analyze_visuals: "Analyzing visuals",
    transcribe: "Transcribing",
    select_candidates: "Finding clips",
    render_previews: "Rendering previews",
  };
  return stage
    ? `${labels[stage.name] ?? stage.name} · ${Math.round(stage.progress * 100)}%`
    : (project.job?.phase ?? "Ready to analyze");
}

export function ProjectQueue({
  projects,
  pendingId,
  onCancel,
  onRetry,
}: {
  projects: Project[];
  pendingId?: string | null;
  onCancel: (id: string) => Promise<unknown>;
  onRetry: (id: string) => Promise<unknown>;
}) {
  const waiting = projects
    .filter((p) => p.status === "queued")
    .toSorted(
      (a, b) =>
        (a.job?.enqueued_at ?? a.created_at).localeCompare(
          b.job?.enqueued_at ?? b.created_at,
        ) || a.id.localeCompare(b.id),
    );
  const running = projects.filter((p) =>
    ["processing", "downloading", "cancel_requested"].includes(p.status),
  );
  const attention = projects.filter((p) =>
    ["failed", "cancelled"].includes(p.status),
  );
  const items = [...running, ...waiting, ...attention];
  return (
    <section
      className="project-queue-panel"
      aria-labelledby="project-queue-title"
    >
      <div className="queue-panel-heading">
        <div>
          <span className="eyebrow">BACKGROUND WORK</span>
          <h2 id="project-queue-title">Project queue</h2>
          <p>One project at a time. Your next project starts automatically.</p>
        </div>
        <div className="queue-counts">
          <span>
            <strong>{running.length}</strong> running
          </span>
          <span>
            <strong>{waiting.length}</strong> waiting
          </span>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="queue-empty">
          <span aria-hidden="true">✓</span>
          <p>All caught up. Add a URL or upload a video to get started.</p>
        </div>
      ) : (
        <ol className="project-queue-list">
          {items.map((project) => {
            const position =
              waiting.findIndex((item) => item.id === project.id) + 1;
            const retryable = ["failed", "cancelled"].includes(project.status);
            const paused = project.status === "cancelled";
            const stopping = project.status === "cancel_requested";
            return (
              <li key={project.id} className={`queue-item ${project.status}`}>
                <span
                  className="queue-position"
                  aria-label={
                    position ? `Queue position ${position}` : project.status
                  }
                >
                  {position || (retryable ? "!" : "●")}
                </span>
                <div className="queue-item-detail">
                  <Link href={`/projects/${project.id}`}>{project.title}</Link>
                  <span>
                    {position ? `#${position} in queue` : projectPhase(project)}
                  </span>
                  {project.job?.error && (
                    <small className="error">{project.job.error}</small>
                  )}
                </div>
                <button
                  type="button"
                  className="secondary"
                  disabled={pendingId === project.id || stopping}
                  onClick={() =>
                    void (retryable
                      ? onRetry(project.id)
                      : onCancel(project.id))
                  }
                  aria-label={`${paused ? "Resume" : retryable ? "Retry" : "Pause"} ${project.title}`}
                >
                  {stopping
                    ? "Pausing…"
                    : paused
                      ? "Resume"
                      : retryable
                        ? "Retry"
                        : "Pause"}
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

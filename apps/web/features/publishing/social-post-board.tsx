"use client";
import { useState } from "react";
import { ActionLink } from "../../components/action-link";
import { useProjectWorkbench } from "../projects/use-project-workbench";
import { PostControls } from "./post-controls";

export function SocialPostBoard({
  initialClipId = "",
}: {
  initialClipId?: string;
}) {
  const workbench = useProjectWorkbench(undefined, { loadAccounts: true });
  const [query, setQuery] = useState("");
  const [clipFilter, setClipFilter] = useState(initialClipId);
  const [platform, setPlatform] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<string[]>([]);
  const groups = workbench.projects
    .flatMap((project) =>
      project.clips.map((clip) => ({
        project,
        clip,
        posts: clip.publications.filter(
          (post) =>
            (!platform || post.platform === platform) &&
            (!status || post.status === status),
        ),
      })),
    )
    .filter(
      ({ project, clip, posts }) =>
        (!clipFilter || clip.id === clipFilter) &&
        posts.length &&
        `${project.title} ${clip.plan.suggested_title ?? ""} ${posts.map((p) => p.title).join(" ")}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    );
  const current = Math.min(
    page,
    Math.max(0, Math.ceil(groups.length / 10) - 1),
  );
  return (
    <main className="page social-post-board">
      <header className="topbar">
        <div>
          <span className="eyebrow">PUBLISHED & CONNECTED</span>
          <h1>Manage social posts</h1>
          <p>
            Update the existing post, compare destinations, or manage a platform
            deletion.
          </p>
        </div>
        <div className="inline-actions">
          <ActionLink href="/publishing" icon="＋">
            Publish clips
          </ActionLink>
          <ActionLink href="/insights" icon="▥">
            Insights
          </ActionLink>
          <ActionLink href="/settings/accounts" icon="⚙">
            Accounts
          </ActionLink>
        </div>
      </header>
      {clipFilter && (
        <p>
          Showing the selected clip.{" "}
          <button
            type="button"
            onClick={() => {
              setClipFilter("");
              window.history.replaceState(null, "", "/publishing/posts");
            }}
          >
            Show all clips
          </button>
        </p>
      )}
      <div className="board-filters">
        <label>
          Find a clip
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
            placeholder="Search clips or projects"
          />
        </label>
        <label>
          Platform
          <select
            value={platform}
            onChange={(e) => {
              setPlatform(e.target.value);
              setPage(0);
            }}
          >
            <option value="">All platforms</option>
            {["youtube", "instagram", "facebook", "tiktok", "x"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          Post status
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(0);
            }}
          >
            <option value="">All statuses</option>
            {[
              "published",
              "queued",
              "processing",
              "failed",
              "deleted",
              "uncertain",
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      {workbench.loading && <p role="status">Loading social posts…</p>}
      {workbench.error && <p role="alert">{workbench.error}</p>}
      {!groups.length && !workbench.loading && (
        <div className="empty-state">
          <h2>No posts match</h2>
          <p>
            Publish a clip or adjust these filters to manage its destinations.
          </p>
          <ActionLink href="/publishing">Open publishing</ActionLink>
        </div>
      )}
      {groups
        .slice(current * 10, current * 10 + 10)
        .map(({ project, clip, posts }) => (
          <details
            className="clip-insight-group"
            key={`${project.id}:${clip.id}`}
            onToggle={(event) => {
              const open = event.currentTarget.open;
              setExpanded((current) =>
                current.includes(clip.id) === open
                  ? current
                  : open
                    ? [...current, clip.id]
                    : current.filter((id) => id !== clip.id),
              );
            }}
          >
            <summary>
              <span className="clip-insight-name">
                <strong>{clip.plan.suggested_title ?? posts[0].title}</strong>
                <small>
                  {project.title} · {posts.length} destinations
                </small>
              </span>
              <span className="platform-summaries">
                {posts.map((p) => (
                  <span key={p.id} className="platform-pill">
                    {p.platform} · {p.status}
                  </span>
                ))}
              </span>
            </summary>
            <div className="post-destination-grid">
              {expanded.includes(clip.id) &&
                posts.map((post) => (
                  <PostControls
                    key={post.id}
                    revision={JSON.stringify([
                      project.status,
                      clip.plan.suggested_title,
                      clip.plan.suggested_description,
                      clip.plan.hashtags,
                    ])}
                    post={post}
                    onChanged={workbench.replaceProject}
                  />
                ))}
            </div>
            <ActionLink
              href={`/projects/${project.id}/clips/${clip.id}/publish`}
            >
              Open clip publishing
            </ActionLink>
          </details>
        ))}
      {groups.length > 10 && (
        <nav className="pagination" aria-label="Social post pages">
          <button disabled={!current} onClick={() => setPage(current - 1)}>
            ← Previous
          </button>
          <span>
            {current + 1} / {Math.ceil(groups.length / 10)} · {groups.length}{" "}
            clips
          </span>
          <button
            disabled={(current + 1) * 10 >= groups.length}
            onClick={() => setPage(current + 1)}
          >
            Next →
          </button>
        </nav>
      )}
    </main>
  );
}

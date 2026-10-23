"use client";
import { useState } from "react";
import { ActionLink } from "../../components/action-link";
import {
  groupInsightPosts,
  latestSnapshot,
  type InsightPost,
} from "./insight-data";

export function GroupedPerformance({ rows }: { rows: InsightPost[] }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const groups = groupInsightPosts(rows).filter((g) =>
    `${g.title} ${g.rows[0].projectTitle}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const current = Math.min(
    page,
    Math.max(0, Math.ceil(groups.length / 12) - 1),
  );
  return (
    <section
      className="grouped-performance"
      aria-label="Post performance by clip"
    >
      <div className="section-heading">
        <div>
          <h2>Post performance</h2>
          <p>
            One entry per clip. Expand to compare its accounts and platforms.
          </p>
        </div>
        <label className="compact-search">
          Find a clip
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
            placeholder="Search clips"
          />
        </label>
      </div>
      {!groups.length && <p>No published clips match these filters.</p>}
      {groups.slice(current * 12, current * 12 + 12).map((group) => (
        <details className="clip-insight-group" key={group.key}>
          <summary>
            <span className="clip-insight-name">
              <strong>{group.title}</strong>
              <small>
                {group.rows[0].projectTitle} · {group.rows.length} destination
                {group.rows.length === 1 ? "" : "s"}
              </small>
            </span>
            <span className="platform-summaries">
              {group.rows.map(({ post }) => (
                <span className="platform-pill" key={post.id}>
                  {post.platform}{" "}
                  <b>{latestSnapshot(post)?.views.toLocaleString() ?? "—"}</b>
                </span>
              ))}
            </span>
            <span className="clip-insight-total">
              <strong>{group.totals.views.toLocaleString()}</strong>
              <small>
                combined views · {group.totals.tracked}/{group.rows.length}{" "}
                tracked
              </small>
            </span>
          </summary>
          <div className="insight-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Destination</th>
                  <th>Views</th>
                  <th>Engagement</th>
                  <th>Shares</th>
                  <th>Watch time</th>
                  <th>Revenue</th>
                  <th>Last measured</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map(({ post }) => {
                  const m = latestSnapshot(post);
                  return (
                    <tr key={post.id}>
                      <td>
                        <strong>{post.platform}</strong>
                        <small>
                          {post.account_label ?? "Historical account"}
                        </small>
                        {post.post_url && (
                          <a
                            className="inline-post-link"
                            href={post.post_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            View original ↗
                          </a>
                        )}
                      </td>
                      <td>{m?.views.toLocaleString() ?? "—"}</td>
                      <td>
                        {m?.views
                          ? `${(((m.likes + m.comments + m.shares) / m.views) * 100).toFixed(1)}%`
                          : "—"}
                      </td>
                      <td>{m?.shares.toLocaleString() ?? "—"}</td>
                      <td>
                        {m?.average_watch_seconds != null
                          ? `${m.average_watch_seconds.toFixed(1)}s average`
                          : m?.watch_time_seconds != null
                            ? `${m.watch_time_seconds.toLocaleString()}s total`
                            : "—"}
                      </td>
                      <td>
                        {m
                          ? new Intl.NumberFormat("en", {
                              style: "currency",
                              currency: m.currency,
                            }).format(m.revenue)
                          : "—"}
                      </td>
                      <td>
                        {m
                          ? new Date(m.recorded_at).toLocaleString()
                          : "Not measured"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="inline-actions">
            <ActionLink
              href={`/projects/${group.rows[0].projectId}/clips/${group.rows[0].clipId}/publish`}
              icon="↗"
            >
              Open publishing
            </ActionLink>
            <ActionLink
              href={`/publishing/posts?clip=${encodeURIComponent(group.rows[0].clipId)}`}
              icon="⚙"
            >
              Manage social posts
            </ActionLink>
          </div>
        </details>
      ))}
      {groups.length > 12 && (
        <nav className="pagination" aria-label="Clip pages">
          <button disabled={current === 0} onClick={() => setPage(current - 1)}>
            ← Previous
          </button>
          <span>
            {current + 1} / {Math.ceil(groups.length / 12)} · {groups.length}{" "}
            clips
          </span>
          <button
            disabled={(current + 1) * 12 >= groups.length}
            onClick={() => setPage(current + 1)}
          >
            Next →
          </button>
        </nav>
      )}
    </section>
  );
}

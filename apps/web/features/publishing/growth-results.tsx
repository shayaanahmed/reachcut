"use client";
import Link from "next/link";
import { useState } from "react";
import type { GrowthDiagnosis } from "./growth-api";

export function GrowthDiagnosisList({ rows }: { rows: GrowthDiagnosis[] }) {
  const [page, setPage] = useState(0);
  if (!rows.length)
    return (
      <p>
        No post diagnosis yet. Publish a clip and save metrics to start
        learning.
      </p>
    );
  const grouped = new Map<string, GrowthDiagnosis[]>();
  for (const row of rows) {
    const key = `${row.project_id}:${row.clip_id}`;
    grouped.set(key, [...(grouped.get(key) ?? []), row]);
  }
  const groups = [...grouped.entries()];
  const current = Math.min(
    page,
    Math.max(0, Math.ceil(groups.length / 12) - 1),
  );
  return (
    <section aria-label="Post growth diagnosis">
      <h3>What to test next</h3>
      <p>
        Expand a clip to compare its destinations. Baselines use earlier posts
        on the same account at a similar age; these comparisons are
        observations.
      </p>
      {groups
        .slice(current * 12, current * 12 + 12)
        .map(([key, destinations]) => (
          <details className="clip-insight-group" key={key}>
            <summary>
              <span className="clip-insight-name">
                <strong>{destinations[0].title}</strong>
                <small>
                  {destinations.length} destinations ·{" "}
                  {destinations
                    .reduce((n, r) => n + r.views, 0)
                    .toLocaleString()}{" "}
                  combined views
                </small>
              </span>
              <span className="platform-summaries">
                {destinations.map((row) => (
                  <span className="platform-pill" key={row.publication_id}>
                    {row.platform} <b>{row.views.toLocaleString()}</b>
                  </span>
                ))}
              </span>
            </summary>
            {destinations.map((row) => (
              <article className="growth-result" key={row.publication_id}>
                <Link
                  className="inline-post-link"
                  href={`/projects/${row.project_id}/clips/${row.clip_id}/publish`}
                >
                  {row.platform} · {row.title} ↗
                </Link>
                <p>
                  {row.views.toLocaleString()} views · {row.confidence}
                  {row.relative_views !== null
                    ? ` · ${row.relative_views.toFixed(1)}× account median`
                    : ""}
                </p>
                <ul>
                  {row.findings.map((finding) => (
                    <li key={finding}>{finding}</li>
                  ))}
                </ul>
                {row.average_watch_seconds !== null && (
                  <p>
                    Average watch time: {row.average_watch_seconds.toFixed(1)}s
                  </p>
                )}
                {row.sends_per_reach !== null && (
                  <p>
                    Sends per reach: {(row.sends_per_reach * 100).toFixed(2)}%
                  </p>
                )}
                {row.search_share !== null && (
                  <p>
                    Views from search: {(row.search_share * 100).toFixed(1)}%
                  </p>
                )}
                <p>
                  <strong>Next test:</strong> {row.actions.join(" ")}
                </p>
              </article>
            ))}
          </details>
        ))}
      {groups.length > 12 && (
        <nav className="pagination" aria-label="Growth pages">
          <button disabled={!current} onClick={() => setPage(current - 1)}>
            ← Previous
          </button>
          <span>
            {current + 1} / {Math.ceil(groups.length / 12)}
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

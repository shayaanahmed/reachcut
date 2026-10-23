"use client";
import { ActionLink } from "../../components/action-link";
import { GroupedPerformance } from "./grouped-performance";
import { GrowthInsights } from "./growth-insights";
import { useState } from "react";
import { useProjectWorkbench } from "../projects/use-project-workbench";
import {
  insightPosts,
  latestSnapshot,
  summarizeInsights,
  viewsTimeline,
} from "./insight-data";

const count = (n: number) => n.toLocaleString();
const money = (n: number, currency: string) =>
  new Intl.NumberFormat("en", { style: "currency", currency }).format(n);
export function InsightsWorkspace({
  view = "performance",
}: {
  view?: "performance" | "growth";
}) {
  const workbench = useProjectWorkbench(undefined, { loadAccounts: true });
  const [platform, setPlatform] = useState("");
  const [group, setGroup] = useState("");
  const [account, setAccount] = useState("");
  const [days, setDays] = useState("30");
  const [now, setNow] = useState(() => new Date());
  const [refreshing, setRefreshing] = useState(false);
  const [manualErrors, setManualErrors] = useState<Record<string, string>>({});
  const all = insightPosts(workbench.projects);
  const historicalAccounts = [
    ...new Map([
      ...all
        .filter((row) => row.post.social_account_id)
        .map(
          (row) =>
            [
              row.post.social_account_id!,
              `${row.post.account_label ?? "Historical account"} · ${row.post.platform} (history)`,
            ] as const,
        ),
      ...workbench.accounts.map(
        (a) => [a.id, `${a.label} · ${a.platform}`] as const,
      ),
    ]).entries(),
  ];
  const members = workbench.groups.find((g) => g.id === group)?.account_ids;
  const rows = all.filter(
    ({ post }) =>
      (!platform || post.platform === platform) &&
      (!account || post.social_account_id === account) &&
      (!group || members?.includes(post.social_account_id ?? "")),
  );
  const totals = summarizeInsights(rows);
  const engagements = totals.likes + totals.comments + totals.shares;
  const start = days
    ? new Date(now.getTime() - (Number(days) - 1) * 86400000)
    : null;
  const timeline = viewsTimeline(rows, start, now).filter(
    (point) => point.tracked > 0,
  );
  const maxViews = Math.max(1, ...timeline.map((p) => p.views));
  const coordinates = timeline.map(
    (point, i) =>
      `${48 + (i / Math.max(1, timeline.length - 1)) * 866},${225 - (point.views / maxViews) * 185}`,
  );
  const lastSync = rows
    .map(({ post }) => latestSnapshot(post)?.recorded_at)
    .filter((value): value is string => !!value)
    .toSorted()
    .at(-1);
  const warnings = { ...workbench.metricsWarnings, ...manualErrors };
  const syncIssues = new Map<
    string,
    { label: string; message: string; count: number }
  >();
  for (const [id, message] of Object.entries(warnings)) {
    const publication = all.find((row) => row.post.id === id)?.post;
    const key = `${publication?.social_account_id ?? id}:${message}`;
    const existing = syncIssues.get(key);
    syncIssues.set(key, {
      label: publication?.account_label ?? "Account",
      message,
      count: (existing?.count ?? 0) + 1,
    });
  }
  const readyAccounts = new Set(
    workbench.accounts
      .filter((a) => a.is_active && a.connection_status === "connected")
      .map((a) => a.id),
  );
  async function refresh() {
    setRefreshing(true);
    const errors: Record<string, string> = {};
    try {
      for (const { post } of rows) {
        if (
          !readyAccounts.has(post.social_account_id ?? "") ||
          !["youtube", "instagram", "facebook"].includes(post.platform)
        )
          continue;
        const updated = await workbench.syncPublishedMetrics(post.id);
        if (!updated)
          errors[post.id] =
            "Could not refresh this post. Check the account connection and permissions.";
      }
      setManualErrors(errors);
      setNow(new Date());
    } finally {
      setRefreshing(false);
    }
  }
  return (
    <main className="page insights-page">
      <header className="topbar">
        <div>
          <span className="eyebrow">MEASURE & LEARN</span>
          <h1>
            {view === "growth" ? "Growth & experiments" : "Views & insights"}
          </h1>
          <p>Compare channels and posts using saved platform snapshots.</p>
        </div>
        <div className="inline-actions">
          <ActionLink href="/publishing" icon="↗">
            Publishing
          </ActionLink>
          <ActionLink
            href={view === "growth" ? "/insights" : "/growth"}
            icon={view === "growth" ? "▥" : "✦"}
          >
            {view === "growth" ? "Post performance" : "Growth & experiments"}
          </ActionLink>
          <button
            disabled={refreshing || !rows.length}
            onClick={() => void refresh()}
          >
            {refreshing ? "Refreshing…" : "Refresh connected accounts"}
          </button>
        </div>
      </header>
      {workbench.loading && <p className="loading-card">Loading insights…</p>}
      {workbench.error && (
        <p role="alert" className="error">
          {workbench.error}
        </p>
      )}
      <section className="insight-filters" aria-label="Insights filters">
        <label>
          Platform
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          >
            <option value="">All platforms</option>
            {["youtube", "instagram", "facebook", "tiktok", "x"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          Social group
          <select value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">All groups</option>
            {workbench.groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Account
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">All accounts (including history)</option>
            {historicalAccounts.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Chart period
          <select value={days} onChange={(e) => setDays(e.target.value)}>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="">All saved history (up to 1 year)</option>
          </select>
        </label>
      </section>
      <div className="stats-grid insight-totals">
        <article className="stat-primary">
          <span>Total views</span>
          <strong>{count(totals.views)}</strong>
          <small>
            Latest lifetime totals · {totals.tracked} of {rows.length} posts
            tracked
          </small>
        </article>
        <article>
          <span>Engagement rate</span>
          <strong>
            {totals.views
              ? ((engagements / totals.views) * 100).toFixed(1)
              : "0.0"}
            %
          </strong>
          <small>(likes + comments + shares) ÷ views</small>
        </article>
        <article>
          <span>Published posts</span>
          <strong>{rows.length}</strong>
          <small>
            {rows.length - totals.tracked} awaiting their first snapshot
          </small>
        </article>
        <article>
          <span>Tracked revenue</span>
          <strong>
            {Object.entries(totals.revenue)
              .map(([currency, value]) => money(value, currency))
              .join(" · ") || "—"}
          </strong>
          <small>Currencies kept separate</small>
        </article>
      </div>
      {view === "growth" ? (
        <GrowthInsights
          publicationIds={rows.map((r) => r.post.id)}
          refreshKey={lastSync ?? ""}
        />
      ) : (
        <GroupedPerformance
          key={`${platform}:${account}:${group}`}
          rows={rows}
        />
      )}
      {view === "performance" && (
        <details className="insight-trend-disclosure">
          <summary>Views over time · explore the trend chart</summary>
          <section
            className="insight-chart-panel"
            aria-labelledby="views-chart-title"
          >
            <div className="section-heading">
              <div>
                <h2 id="views-chart-title">Views over time</h2>
                <p>
                  Cumulative recorded views. Saved values carry forward between
                  syncs; this is not daily new views.
                </p>
              </div>
              <small>
                Last snapshot:{" "}
                {lastSync
                  ? new Date(lastSync).toLocaleString()
                  : "Not synced yet"}
              </small>
            </div>
            {!timeline.length ? (
              <div className="empty-state compact">
                <h3>No metrics yet</h3>
                <p>
                  Publish a clip and refresh its insights, or add a manual
                  snapshot on its publishing page.
                </p>
                <ActionLink href="/publishing">Open publishing</ActionLink>
              </div>
            ) : (
              <>
                <svg
                  viewBox="0 0 960 275"
                  role="img"
                  aria-labelledby="views-chart-label"
                >
                  <title id="views-chart-label">
                    Cumulative views: {count(timeline[0].views)} to{" "}
                    {count(timeline.at(-1)?.views ?? 0)}
                  </title>
                  {[0, 0.5, 1].map((f) => (
                    <g key={f}>
                      <line
                        x1="48"
                        x2="914"
                        y1={225 - f * 185}
                        y2={225 - f * 185}
                        stroke="currentColor"
                        opacity="0.12"
                      />
                      <text
                        x="4"
                        y={230 - f * 185}
                        fontSize="12"
                        fill="currentColor"
                      >
                        {new Intl.NumberFormat("en", {
                          notation: "compact",
                        }).format(maxViews * f)}
                      </text>
                    </g>
                  ))}
                  <polyline
                    points={coordinates.join(" ")}
                    fill="none"
                    stroke="#6d65f5"
                    strokeWidth="3"
                  />
                  {timeline.map((p, i) => (
                    <circle
                      key={p.date}
                      cx={48 + (i / Math.max(1, timeline.length - 1)) * 866}
                      cy={225 - (p.views / maxViews) * 185}
                      r={timeline.length > 90 ? 1.5 : 3}
                      fill="#6d65f5"
                    >
                      <title>
                        {p.date}: {count(p.views)} views · {p.tracked} tracked
                        posts
                      </title>
                    </circle>
                  ))}
                  <text x="48" y="260" fontSize="12" fill="currentColor">
                    {timeline[0].date}
                  </text>
                  <text
                    x="914"
                    y="260"
                    textAnchor="end"
                    fontSize="12"
                    fill="currentColor"
                  >
                    {timeline.at(-1)?.date}
                  </text>
                </svg>
                <details>
                  <summary>View chart data</summary>
                  <div className="insight-table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Date (UTC)</th>
                          <th>Recorded views</th>
                          <th>Tracked posts</th>
                        </tr>
                      </thead>
                      <tbody>
                        {timeline.map((p) => (
                          <tr key={p.date}>
                            <td>{p.date}</td>
                            <td>{count(p.views)}</td>
                            <td>{p.tracked}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </>
            )}
          </section>
        </details>
      )}
      <details className="secondary-metrics">
        <summary>More engagement & business metrics</summary>
        <section className="insight-detail-grid" aria-label="Detailed metrics">
          {[
            ["Likes", totals.likes],
            ["Comments", totals.comments],
            ["Shares", totals.shares],
            ["Followers gained", totals.followers],
            [
              "Watch time (hours)",
              Number((totals.watchSeconds / 3600).toFixed(1)),
            ],
            ["Affiliate clicks", totals.clicks],
            ["Conversions", totals.conversions],
          ].map(([label, value]) => (
            <article key={String(label)}>
              <span>{label}</span>
              <strong>{count(Number(value))}</strong>
            </article>
          ))}
        </section>
      </details>
      <details className="metrics-help">
        <summary>About these metrics</summary>
        <p className="muted">
          YouTube, Instagram, and Facebook refresh through their connected
          accounts. Other platforms and revenue, shares, watch time, followers,
          and conversions may require manual snapshots. Zero means no value has
          been recorded; it does not confirm the platform reported zero.
        </p>
      </details>
      {Object.keys(warnings).length > 0 && (
        <details className="sync-warnings" aria-label="Account sync status">
          <summary>
            {syncIssues.size} account sync issue
            {syncIssues.size === 1 ? "" : "s"} need attention
          </summary>
          <p>
            Other posts continue refreshing. Your saved metrics remain
            available.
          </p>
          <ul>
            {[...syncIssues.entries()].map(([key, issue]) => (
              <li key={key}>
                <strong>
                  {issue.label} ({issue.count}{" "}
                  {issue.count === 1 ? "post" : "posts"}):
                </strong>{" "}
                {issue.message}
              </li>
            ))}
          </ul>
          <ActionLink href="/settings/accounts" icon="⚙">
            Review account connections
          </ActionLink>
        </details>
      )}
    </main>
  );
}

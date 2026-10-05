import type { Project } from "../../lib/contracts";

type Publication = Project["clips"][number]["publications"][number];

function latestMetrics(publication: Publication) {
  return publication.metric_snapshots.at(-1);
}

function formatMoney(amount: number, currency: string) {
  return new Intl.NumberFormat("en", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function ProjectPerformance({ project }: { project: Project }) {
  const rows = project.clips.flatMap((clip, clipIndex) =>
    clip.publications
      .filter((publication) => publication.status === "published")
      .map((publication) => ({
        clip,
        clipIndex,
        publication,
        metrics: latestMetrics(publication),
      })),
  );
  if (rows.length === 0) return null;

  const totals = rows.reduce(
    (result, row) => {
      if (!row.metrics) return result;
      result.views += row.metrics.views;
      result.engagements +=
        row.metrics.likes + row.metrics.comments + row.metrics.shares;
      result.revenue += row.metrics.revenue;
      result.currencies.add(row.metrics.currency);
      return result;
    },
    { views: 0, engagements: 0, revenue: 0, currencies: new Set<string>() },
  );
  const currency =
    totals.currencies.size === 1 ? [...totals.currencies][0] : "EUR";
  const engagementRate = totals.views
    ? (totals.engagements / totals.views) * 100
    : 0;
  const rpm = totals.views ? (totals.revenue / totals.views) * 1000 : 0;
  const mixedCurrencies = totals.currencies.size > 1;

  return (
    <section className="performance-panel" aria-labelledby="performance-title">
      <div className="performance-heading">
        <div>
          <span className="eyebrow">PROJECT PERFORMANCE</span>
          <h2 id="performance-title">Publishing results</h2>
        </div>
        <small>Latest saved snapshot from each published clip</small>
      </div>
      <div className="performance-grid">
        <article>
          <span>Published posts</span>
          <strong>{rows.length}</strong>
        </article>
        <article>
          <span>Total views</span>
          <strong>{totals.views.toLocaleString()}</strong>
        </article>
        <article>
          <span>Engagement rate</span>
          <strong>{engagementRate.toFixed(1)}%</strong>
        </article>
        <article>
          <span>Tracked revenue</span>
          <strong>
            {mixedCurrencies
              ? "Mixed currencies"
              : formatMoney(totals.revenue, currency)}
          </strong>
          <small>
            {mixedCurrencies
              ? "RPM unavailable across currencies"
              : `${formatMoney(rpm, currency)} per 1,000 views`}
          </small>
        </article>
      </div>
      <div className="performance-table">
        <div className="performance-table-head" aria-hidden="true">
          <span>Clip</span>
          <span>Platform</span>
          <span>Views</span>
          <span>Engagement</span>
          <span>Revenue</span>
        </div>
        {rows.map(({ clip, clipIndex, publication, metrics }) => (
          <article key={publication.id}>
            <span>
              <strong>
                {clip.plan.suggested_title ?? `Candidate ${clipIndex + 1}`}
              </strong>
              <small>
                {publication.account_label
                  ? `${publication.account_label} · ${publication.title}`
                  : publication.title}
              </small>
            </span>
            <span className={`platform-badge ${publication.platform}`}>
              {publication.platform}
            </span>
            <span>{metrics?.views.toLocaleString() ?? "—"}</span>
            <span>
              {metrics && metrics.views
                ? `${(
                    ((metrics.likes + metrics.comments + metrics.shares) /
                      metrics.views) *
                    100
                  ).toFixed(1)}%`
                : "—"}
            </span>
            <span>
              {metrics ? formatMoney(metrics.revenue, metrics.currency) : "—"}
            </span>
          </article>
        ))}
      </div>
    </section>
  );
}

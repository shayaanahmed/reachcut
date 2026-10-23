import type { Project } from "../../lib/contracts";
export type InsightPost = {
  projectId: string;
  projectTitle: string;
  clipId: string;
  post: Project["clips"][number]["publications"][number];
};
export function insightPosts(projects: Project[]): InsightPost[] {
  return projects.flatMap((project) =>
    project.clips.flatMap((clip) =>
      clip.publications
        .filter((post) => post.status === "published")
        .map((post) => ({
          projectId: project.id,
          projectTitle: project.title,
          clipId: clip.id,
          post,
        })),
    ),
  );
}
export function latestSnapshot(post: InsightPost["post"]) {
  return post.metric_snapshots
    .toSorted((a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at))
    .at(-1);
}
export function summarizeInsights(rows: InsightPost[]) {
  const revenue: Record<string, number> = {};
  const totals = {
    views: 0,
    likes: 0,
    comments: 0,
    shares: 0,
    followers: 0,
    watchSeconds: 0,
    clicks: 0,
    conversions: 0,
    tracked: 0,
    revenue,
  };
  for (const { post } of rows) {
    const m = latestSnapshot(post);
    if (!m) continue;
    totals.tracked++;
    totals.views += m.views;
    totals.likes += m.likes;
    totals.comments += m.comments;
    totals.shares += m.shares;
    totals.followers += m.followers_gained;
    totals.watchSeconds += m.watch_time_seconds ?? 0;
    totals.clicks += m.affiliate_clicks;
    totals.conversions += m.conversions;
    revenue[m.currency] = (revenue[m.currency] ?? 0) + m.revenue;
  }
  return totals;
}
// Each point uses the last known snapshot of each post. Repeated cumulative
// snapshots are never summed together as if they were additional daily views.
export function viewsTimeline(
  rows: InsightPost[],
  start: Date | null,
  end: Date,
) {
  const snapshots = rows.flatMap((row) => row.post.metric_snapshots);
  if (!snapshots.length) return [];
  const earliest = new Date(
    Math.min(...snapshots.map((m) => Date.parse(m.recorded_at))),
  );
  const first = new Date(start ?? earliest);
  first.setUTCHours(0, 0, 0, 0);
  const last = new Date(end);
  last.setUTCHours(23, 59, 59, 999);
  // Limit very old workspaces to the latest year; filters still preserve totals.
  first.setTime(Math.max(first.getTime(), last.getTime() - 365 * 86400000));
  first.setUTCHours(0, 0, 0, 0);
  const sorted = rows.map(({ post }) =>
    post.metric_snapshots.toSorted(
      (a, b) => Date.parse(a.recorded_at) - Date.parse(b.recorded_at),
    ),
  );
  const points: { date: string; views: number; tracked: number }[] = [];
  for (let day = first.getTime(); day <= last.getTime(); day += 86400000) {
    const cutoff = day + 86400000 - 1;
    let views = 0,
      tracked = 0;
    for (const history of sorted) {
      const latest = history.findLast(
        (m) => Date.parse(m.recorded_at) <= cutoff,
      );
      if (latest) {
        views += latest.views;
        tracked++;
      }
    }
    points.push({
      date: new Date(day).toISOString().slice(0, 10),
      views,
      tracked,
    });
  }
  return points;
}

export function groupInsightPosts(rows: InsightPost[]) {
  const groups = new Map<
    string,
    { key: string; title: string; rows: InsightPost[] }
  >();
  for (const row of rows) {
    const key = `${row.projectId}:${row.clipId}`;
    const group = groups.get(key) ?? {
      key,
      title: row.post.title || row.projectTitle,
      rows: [],
    };
    group.rows.push(row);
    groups.set(key, group);
  }
  return [...groups.values()]
    .map((group) => ({ ...group, totals: summarizeInsights(group.rows) }))
    .toSorted((a, b) => b.totals.views - a.totals.views);
}

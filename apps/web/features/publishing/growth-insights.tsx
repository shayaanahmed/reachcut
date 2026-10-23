"use client";
import { useEffect, useState } from "react";
import { loadGrowthInsights, type GrowthDiagnosis } from "./growth-api";
import { GrowthDiagnosisList } from "./growth-results";

export function GrowthInsights({
  publicationIds,
  refreshKey,
}: {
  publicationIds: string[];
  refreshKey: string;
}) {
  const [rows, setRows] = useState<GrowthDiagnosis[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    loadGrowthInsights()
      .then((data) => {
        if (active) {
          setRows(data);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      active = false;
    };
  }, [refreshKey]);
  const selected = rows.filter((r) =>
    publicationIds.includes(r.publication_id),
  );
  const comparable = selected.filter((r) => r.relative_views !== null);
  const views = selected.map((r) => r.views).sort((a, b) => a - b);
  const median = views.length
    ? (views[Math.floor((views.length - 1) / 2)] +
        views[Math.floor(views.length / 2)]) /
      2
    : null;
  return (
    <section className="growth-panel">
      <h2>Growth experiments</h2>
      <p>
        Goal: raise typical views and the share of posts that outperform your
        own account history.
      </p>
      <p>
        Median recorded views:{" "}
        <strong>
          {median === null ? "Not measured" : median.toLocaleString()}
        </strong>{" "}
        · Posts at least 2× account median:{" "}
        <strong>
          {comparable.filter((r) => r.relative_views! >= 2).length} /{" "}
          {comparable.length} comparable posts
        </strong>{" "}
        · Posts reaching 100,000 views:{" "}
        <strong>{selected.filter((r) => r.views >= 100000).length}</strong>
      </p>
      <p>
        Uses latest lifetime snapshots. Post ages differ; the 2× measure is an
        experimental target, not a platform ranking threshold.
      </p>
      {error && <p role="alert">{error}</p>}
      <GrowthDiagnosisList rows={selected} />
    </section>
  );
}

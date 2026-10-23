"use client";
import { useEffect, useState } from "react";
import { getQualityReview } from "./api";
import type { QualityReview } from "./api";

export function QualityReviewDetails({ projectId }: { projectId: string }) {
  const [review, setReview] = useState<QualityReview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void getQualityReview(projectId)
      .then((value) => {
        if (alive) setReview(value);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [projectId]);
  return (
    <details>
      <summary>Quality review findings</summary>
      {error && <p role="alert">{error}</p>}
      <p>{review?.limitations ?? "Loading quality checks…"}</p>
      {review?.clips.map((clip, index) => (
        <article key={clip.clip_id}>
          <h3>Clip {index + 1}</h3>
          {clip.findings.length ? (
            clip.findings.map((finding, i) => (
              <p key={i}>
                {finding.severity} · {finding.start.toFixed(1)}s:{" "}
                {finding.message} ({finding.basis})
              </p>
            ))
          ) : (
            <p>
              Available checks passed. Review framing, captions and context
              before approval.
            </p>
          )}
          {clip.corrections.map((correction) => (
            <p key={correction.attempt}>
              Correction {correction.attempt}: {correction.action}
            </p>
          ))}
        </article>
      ))}
    </details>
  );
}

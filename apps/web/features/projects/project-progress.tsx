"use client";

import { useEffect, useState } from "react";
import { projectPhase } from "./project-queue";

import type { Project } from "../../lib/contracts";

const STAGE_ORDER = [
  "probe",
  "analyze_visuals",
  "transcribe",
  "select_candidates",
  "render_previews",
  "quality_review",
] as const;

const STAGE_LABELS: Record<string, string> = {
  localize: "Translate language version & prepare preview",
  generate_metadata: "Write publishing details",
  optimize_growth: "Optimize audience, SEO & growth",
  probe: "Inspect media",
  analyze_visuals: "Track faces & action",
  transcribe: "Transcribe locally",
  select_candidates: "Find highlights",
  render_previews: "Render previews",
  quality_review: "Check rendered clips",
};

function stageOrder(project: Project): readonly string[] {
  return project.job?.processing_mode === "language"
    ? ["probe", "transcribe", "generate_metadata", "localize"]
    : project.job?.processing_mode === "metadata"
      ? ["probe", "transcribe", "generate_metadata", "optimize_growth"]
      : project.job
        ? [...STAGE_ORDER, "generate_metadata", "optimize_growth"]
        : STAGE_ORDER;
}

function projectProgress(project: Project): number {
  const order = stageOrder(project);
  const progress = order.reduce((total, name) => {
    const stage = project.stages.find((item) => item.name === name);
    if (stage?.status === "succeeded") return total + 1;
    if (stage?.status === "running") return total + stage.progress;
    return total;
  }, 0);
  return progress / order.length;
}

export function ProjectProgress({ project }: { project: Project }) {
  const [now, setNow] = useState(0);
  const active = ["processing", "downloading", "cancel_requested"].includes(
    project.status,
  );
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  const progress = ["queued", "downloading"].includes(project.status)
    ? 0
    : projectProgress(project);
  return (
    <div className="pipeline" aria-label="Analysis progress">
      <div className="pipeline-summary">
        <strong>{projectPhase(project)}</strong>
        <span>{Math.round(progress * 100)}%</span>
      </div>
      {project.job?.error && (
        <p className="error" role="alert">
          {project.job.error}
        </p>
      )}
      <progress max={1} value={project.status === "queued" ? 0 : progress} />
      <details>
        <summary>Processing details</summary>
        <div className="stage-list">
          {stageOrder(project).map((name) => {
            const stage = project.stages.find((item) => item.name === name);
            const message =
              typeof stage?.error?.message === "string"
                ? stage.error.message
                : null;
            return (
              <div className={`stage ${stage?.status ?? "pending"}`} key={name}>
                <span className="stage-dot" aria-hidden="true" />
                <div>
                  <strong>{STAGE_LABELS[name]}</strong>
                  <small>
                    {stage?.status === "cancelled" ||
                    (stage?.status === "running" &&
                      project.status === "cancelled")
                      ? "Paused · resumes on restart"
                      : stage?.status === "running"
                        ? `${Math.round(stage.progress * 100)}% · attempt ${stage.attempts}${stage.started_at && now ? ` · ${Math.max(0, Math.floor((now - Date.parse(stage.started_at)) / 1000))}s elapsed` : ""}`
                        : stage?.status === "failed"
                          ? `Failed · attempt ${stage.attempts}`
                          : stage?.status === "succeeded"
                            ? "Complete"
                            : "Waiting"}
                  </small>
                  {message && <p role="alert">{message}</p>}
                </div>
              </div>
            );
          })}
        </div>
      </details>
    </div>
  );
}

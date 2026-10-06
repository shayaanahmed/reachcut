import type { Project } from "../../lib/contracts";

const STAGE_ORDER = [
  "probe",
  "analyze_visuals",
  "transcribe",
  "select_candidates",
  "render_previews",
] as const;

const STAGE_LABELS: Record<(typeof STAGE_ORDER)[number], string> = {
  probe: "Inspect media",
  analyze_visuals: "Track faces & action",
  transcribe: "Transcribe locally",
  select_candidates: "Find highlights",
  render_previews: "Render previews",
};

function projectProgress(project: Project): number {
  const progress = STAGE_ORDER.reduce((total, name) => {
    const stage = project.stages.find((item) => item.name === name);
    if (stage?.status === "succeeded") return total + 1;
    if (stage?.status === "running") return total + stage.progress;
    return total;
  }, 0);
  return progress / STAGE_ORDER.length;
}

export function ProjectProgress({ project }: { project: Project }) {
  const progress = projectProgress(project);
  return (
    <div className="pipeline" aria-label="Analysis progress">
      <div className="pipeline-summary">
        <strong>
          {project.status === "failed"
            ? "Analysis needs attention"
            : project.status === "review"
              ? "Analysis complete"
              : "Analyzing locally"}
        </strong>
        <span>{Math.round(progress * 100)}%</span>
      </div>
      <progress max={1} value={progress} />
      <div className="stage-list">
        {STAGE_ORDER.map((name) => {
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
                  {stage?.status === "running"
                    ? `${Math.round(stage.progress * 100)}% · attempt ${stage.attempts}`
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
    </div>
  );
}

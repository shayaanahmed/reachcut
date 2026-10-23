export function JobProgress({
  kind,
  phase,
}: {
  kind: "ideas" | "storyboard" | "video";
  phase: string;
}) {
  const stages =
    kind === "ideas"
      ? /storyboard|writing|checking the story/i.test(phase)
        ? ["Read repository", "Write storyboard", "Choose template"]
        : ["Read sources", "Find storylines", "Ready to choose"]
      : kind === "storyboard"
        ? ["Write & review", "Design scenes", "Ready to review"]
        : [
            "Prepare scenes",
            "Render video",
            "AI review & refinement",
            "Ready to watch",
          ];
  const current =
    kind === "video" && /AI.*review|refin/i.test(phase)
      ? 2
      : /designing|render|assembl|caption|finding three/i.test(phase)
        ? 1
        : /ready/i.test(phase)
          ? 2
          : 0;
  return (
    <aside className="studio-job-progress" role="status" aria-live="polite">
      <div>
        <span className="studio-job-dot" aria-hidden="true" />
        <strong>{phase}</strong>
        <span>
          Working in the background · you can keep browsing or return later.
        </span>
      </div>
      <ol>
        {stages.map((stage, i) => (
          <li
            key={stage}
            className={i < current ? "done" : i === current ? "current" : ""}
          >
            <b>{i < current ? "✓" : i + 1}</b>
            {stage}
          </li>
        ))}
      </ol>
    </aside>
  );
}

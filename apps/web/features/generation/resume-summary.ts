import type { GeneratedVideo } from "../../lib/contracts";

export function resumeSummary(video: GeneratedVideo) {
  const completed = video.scenes.filter(
    (scene) => scene.status === "complete",
  ).length;
  const failed = video.scenes.find((scene) => scene.status === "failed");
  const next =
    failed ?? video.scenes.find((scene) => scene.status !== "complete");
  return {
    label: next ? `Resume scene ${next.scene_index}` : "Retry final stitching",
    detail: next
      ? `${completed} of ${video.scenes.length} scenes complete. Saved videos and continuity frames will be checked and reused. Only unfinished or invalid work is retried.`
      : "All scenes are saved. Retry final stitching without generating the scenes again.",
  };
}

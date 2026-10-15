import { describe, expect, it } from "vitest";
import type { GeneratedVideo } from "../../lib/contracts";
import { resumeSummary } from "./resume-summary";

describe("Recovery messaging", () => {
  it("identifies the failed scene and preserved progress", () => {
    const video = {
      scenes: [
        { scene_index: 1, status: "complete" },
        { scene_index: 2, status: "complete" },
        { scene_index: 3, status: "failed" },
        { scene_index: 4, status: "queued" },
      ],
    } as GeneratedVideo;
    expect(resumeSummary(video).label).toBe("Resume scene 3");
    expect(resumeSummary(video).detail).toContain("2 of 4 scenes complete");
  });
  it("offers final stitching when all scenes are complete", () => {
    const video = {
      scenes: [
        { scene_index: 1, status: "complete" },
        { scene_index: 2, status: "complete" },
      ],
    } as GeneratedVideo;
    expect(resumeSummary(video).label).toBe("Retry final stitching");
    expect(resumeSummary(video).detail).toContain(
      "without generating the scenes again",
    );
  });
});

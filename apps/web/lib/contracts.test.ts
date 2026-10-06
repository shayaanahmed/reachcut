import { describe, expect, it } from "vitest";
import { projectSchema } from "./contracts";

describe("project contract", () => {
  it("rejects an unknown editing plan version", () => {
    expect(() =>
      projectSchema.parse({ clips: [{ plan: { schema_version: "2.0" } }] }),
    ).toThrow();
  });

  it("keeps social metadata optional for saved editing plans", () => {
    const plan = {
      schema_version: "1.0",
      source: { start_seconds: 0, end_seconds: 30 },
      scores: {
        overall: 80,
        hook: 80,
        clarity: 80,
        payoff: 80,
        visual_interest: 80,
      },
      rationale: "A complete idea.",
      hook: null,
      caption_style: "clean",
      emphasis: [],
      effects: [],
      cta: null,
    };
    const project = projectSchema.parse({
      id: "project-1",
      title: "Project",
      original_filename: "source.mp4",
      status: "ready",
      duration_seconds: 30,
      authorization_confirmed_at: "2026-10-02T10:00:00Z",
      created_at: "2026-10-02T10:00:00Z",
      stages: [],
      clips: [
        {
          id: "clip-1",
          approval_status: "pending",
          plan,
          preview_path: null,
          final_path: null,
        },
      ],
    });

    expect(project.clips[0].plan.suggested_title).toBeNull();
    expect(project.clips[0].plan.hashtags).toEqual([]);
    expect(project.clips[0].plan.optimization_goal).toBe("views");
    expect(project.clips[0].plan.source_slices).toEqual([]);
    expect(project.clips[0].plan.crop_focus_x).toBe(0.5);
    expect(project.clips[0].publications).toEqual([]);
  });
});

import { describe, expect, it } from "vitest";

import { projectSchema } from "../../lib/contracts";
import { updateClipApproval } from "./use-project-workbench";

function project() {
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
    rationale: "Complete clip.",
    hook: null,
    caption_style: "clean",
    emphasis: [],
    effects: [],
    cta: null,
  };
  return projectSchema.parse({
    id: "project-1",
    title: "Project",
    original_filename: "source.mp4",
    status: "review",
    duration_seconds: 60,
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
      {
        id: "clip-2",
        approval_status: "approved",
        plan,
        preview_path: null,
        final_path: null,
      },
    ],
  });
}

describe("project workbench optimistic updates", () => {
  it("updates only the selected clip so concurrent approvals cannot overwrite each other", () => {
    const updated = updateClipApproval([project()], "clip-1", "rejected");

    expect(updated[0].clips.map((clip) => clip.approval_status)).toEqual([
      "rejected",
      "approved",
    ]);
  });
});

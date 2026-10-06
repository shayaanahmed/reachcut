import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Project } from "../../lib/contracts";
import { ClipCard } from "./clip-card";

const clip = {
  id: "clip-1",
  approval_status: "pending",
  preview_path: null,
  final_path: null,
  publications: [],
  plan: {
    schema_version: "1.0",
    source: { start_seconds: 0, end_seconds: 30 },
    source_slices: [],
    optimization_goal: "views",
    content_mode: "auto",
    enhancement_level: "clean",
    scores: {
      overall: 88,
      hook: 88,
      clarity: 88,
      payoff: 88,
      visual_interest: 88,
    },
    rationale: "A clear, self-contained idea.",
    suggested_title: "The Detail Everyone Missed",
    hashtags: ["#UsefulTips", "#MustWatch", "#VideoClip"],
    hook: null,
    caption_style: "clean",
    caption_config: {
      preset: "custom",
      enabled: true,
      position: "bottom",
      font_family: "Noto Sans",
      font_size: 58,
      text_color: "#FFFFFF",
      highlight_color: "#D8FF42",
      outline_color: "#111111",
      animation: "pop",
      highlighted_words: [],
      max_words_per_line: 5,
      text_override: null,
      source_language: null,
      target_language: null,
      translation_mode: "original",
      translated_text: null,
    },
    frame_style: "blurred_background",
    crop_focus_x: 0.5,
    crop_focus_y: 0.5,
    tracking: { enabled: false, strategy: "static", keyframes: [] },
    transition_style: "cut",
    transition_duration_seconds: 0.2,
    secondary_media: [],
    audio_track_index: 0,
    emphasis: [],
    effects: [],
    cta: null,
  },
  publish_recommendation: {
    score: 91,
    confidence: "high",
    reasons: ["Opening hook is 88/100", "30s duration fits short-form viewing"],
  },
} as Project["clips"][number];

describe("clip card", () => {
  it("keeps project review compact and links to the dedicated studio", () => {
    render(
      <ClipCard
        projectId="project-1"
        clip={clip}
        index={0}
        bestToPublish={true}
        approvalPending={false}
        onApprove={vi.fn()}
        onRender={vi.fn()}
      />,
    );

    expect(screen.getByText("The Detail Everyone Missed")).toBeTruthy();
    expect(screen.getByText("Top pick")).toBeTruthy();
    expect(screen.getByText("91")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /Open studio/ }).getAttribute("href"),
    ).toBe("/projects/project-1/clips/clip-1");
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
    expect(screen.queryByText("#UsefulTips #MustWatch #VideoClip")).toBeNull();
  });

  it("shows a per-clip queued render without blocking unrelated review actions", () => {
    const { container } = render(
      <ClipCard
        projectId="project-1"
        clip={{ ...clip, approval_status: "approved" }}
        index={0}
        bestToPublish={false}
        approvalPending={false}
        renderState="queued"
        onApprove={vi.fn()}
        onRender={vi.fn()}
      />,
    );

    const card = within(container);
    expect(
      (
        card.getByRole("button", {
          name: "Final export queued",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      (card.getByRole("button", { name: "Reject" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });
});

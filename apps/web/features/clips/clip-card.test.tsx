import { render, screen } from "@testing-library/react";
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
    },
    frame_style: "blurred_background",
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
  it("shows the suggested social title and hashtags", () => {
    render(
      <ClipCard
        clip={clip}
        accounts={[]}
        index={0}
        bestToPublish={true}
        busy={false}
        onApprove={vi.fn()}
        onRender={vi.fn()}
        onSaveStyle={vi.fn()}
        onPublish={vi.fn()}
        onRecordMetrics={vi.fn()}
        onRefreshPublication={vi.fn()}
        onSyncMetrics={vi.fn()}
        onDeletePublication={vi.fn()}
      />,
    );

    expect(screen.getByText("The Detail Everyone Missed")).toBeTruthy();
    expect(screen.getByText("#UsefulTips #MustWatch #VideoClip")).toBeTruthy();
    expect(screen.getByText("Best to publish")).toBeTruthy();
    expect(screen.getByText(/Publish potential 91\/100/)).toBeTruthy();
    expect(
      (
        screen.getByRole("checkbox", {
          name: /Burn subtitles into this clip/,
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
  });
});

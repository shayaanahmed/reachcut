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
        onTranslate={vi.fn()}
        onTrack={vi.fn()}
        onUploadAsset={vi.fn()}
        onRemoveAsset={vi.fn()}
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
    expect(screen.getByText("Views version")).toBeTruthy();
    expect(screen.getByText(/30.0s render/)).toBeTruthy();
    expect(screen.getByText(/Publish potential 91\/100/)).toBeTruthy();
    expect(
      (
        screen.getByRole("checkbox", {
          name: /Burn subtitles into this clip/,
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    expect(screen.getByLabelText(/Source slices/)).toBeTruthy();
    expect(screen.getByLabelText(/Corrected caption text/)).toBeTruthy();
    expect(screen.getByLabelText(/Content mode/)).toBeTruthy();
    expect(screen.getByLabelText(/Caption preset/)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Analyze face\/action tracking/ }),
    ).toBeTruthy();
    expect(
      screen.getByText(/Add gameplay, B-roll, reaction, SFX or music/),
    ).toBeTruthy();
  });
});

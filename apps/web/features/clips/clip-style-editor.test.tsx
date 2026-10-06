import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { projectSchema } from "../../lib/contracts";
import { ClipStyleEditor } from "./clip-style-editor";

const clip = projectSchema.parse({
  id: "project-1",
  title: "Project",
  original_filename: "source.mp4",
  status: "review",
  duration_seconds: 30,
  authorization_confirmed_at: "2026-10-02T10:00:00Z",
  created_at: "2026-10-02T10:00:00Z",
  stages: [],
  clips: [
    {
      id: "clip-1",
      approval_status: "pending",
      preview_path: "/preview.mp4",
      final_path: null,
      plan: {
        schema_version: "1.0",
        source: { start_seconds: 0, end_seconds: 30 },
        scores: {
          overall: 80,
          hook: 80,
          clarity: 80,
          payoff: 80,
          visual_interest: 80,
        },
        rationale: "A complete thought.",
        hook: {
          text: "Opening",
          start_seconds: 0,
          end_seconds: 2,
          render: true,
        },
        caption_style: "clean",
        emphasis: [],
        effects: [],
        cta: null,
      },
    },
  ],
}).clips[0];

describe("clip style editor", () => {
  afterEach(cleanup);

  it("groups tools into studio tabs and emits instant design-preview changes", () => {
    const onPreviewChange = vi.fn();
    const onDirtyChange = vi.fn();
    render(
      <ClipStyleEditor
        clip={clip}
        saving={false}
        translating={false}
        tracking={false}
        assetBusy={false}
        mutationBusy={false}
        onSave={vi.fn()}
        onTranslate={vi.fn()}
        onTrack={vi.fn()}
        onUploadAsset={vi.fn()}
        onRemoveAsset={vi.fn()}
        onPreviewChange={onPreviewChange}
        onDirtyChange={onDirtyChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Captions/ }));
    fireEvent.change(screen.getByLabelText("Size"), {
      target: { value: "72" },
    });

    expect(screen.getByRole("heading", { name: "Captions" })).toBeTruthy();
    expect(onPreviewChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ fontSize: 72, hookText: "Opening" }),
    );
    expect(onDirtyChange).toHaveBeenLastCalledWith(true);

    fireEvent.click(screen.getByRole("button", { name: "Reset changes" }));
    expect(onDirtyChange).toHaveBeenLastCalledWith(false);
    expect(onPreviewChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ fontSize: 58, hookText: "Opening" }),
    );
  });

  it("replaces the settings form with Assets instead of creating an empty grid row", () => {
    const { container } = render(
      <ClipStyleEditor
        clip={clip}
        saving={false}
        translating={false}
        tracking={false}
        assetBusy={false}
        mutationBusy={false}
        onSave={vi.fn()}
        onTranslate={vi.fn()}
        onTrack={vi.fn()}
        onUploadAsset={vi.fn()}
        onRemoveAsset={vi.fn()}
        onPreviewChange={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Assets/ }));

    expect(
      container.querySelector(".studio-settings-form")?.hasAttribute("hidden"),
    ).toBe(true);
    expect(
      container.querySelector(".assets-panel")?.hasAttribute("hidden"),
    ).toBe(false);
    expect(
      screen.getByRole("heading", { name: "Secondary media" }),
    ).toBeTruthy();
  });
});

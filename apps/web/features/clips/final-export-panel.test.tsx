import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { projectSchema } from "../../lib/contracts";
import { FinalExportPanel } from "./final-export-panel";

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
      approval_status: "approved",
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
        hook: null,
        caption_style: "clean",
        emphasis: [],
        effects: [],
        cta: null,
      },
    },
  ],
}).clips[0];

describe("final export panel", () => {
  it("prevents a stale final render while studio changes are unsaved", () => {
    const onRender = vi.fn();
    render(
      <FinalExportPanel
        clip={clip}
        publishHref="/projects/project-1/clips/clip-1/publish"
        hasUnsavedChanges
        approvalPending={false}
        onApprove={vi.fn().mockResolvedValue(true)}
        onRender={onRender}
      />,
    );

    const button = screen.getByRole("button", {
      name: "Save preview changes first",
    }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(onRender).not.toHaveBeenCalled();
  });

  it("communicates when an approved final render is queued", () => {
    render(
      <FinalExportPanel
        clip={clip}
        publishHref="/projects/project-1/clips/clip-1/publish"
        hasUnsavedChanges={false}
        approvalPending={false}
        renderState="queued"
        onApprove={vi.fn().mockResolvedValue(true)}
        onRender={vi.fn()}
      />,
    );

    expect(screen.getByText("Final video is in the render queue")).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Queued for rendering…",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it("approves and starts the final render as one managed action", async () => {
    const onApprove = vi.fn().mockResolvedValue(true);
    const onRender = vi.fn().mockResolvedValue(undefined);
    render(
      <FinalExportPanel
        clip={{ ...clip, approval_status: "pending" }}
        publishHref="/projects/project-1/clips/clip-1/publish"
        hasUnsavedChanges={false}
        approvalPending={false}
        onApprove={onApprove}
        onRender={onRender}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Approve & render final MP4" }),
    );

    await waitFor(() => expect(onRender).toHaveBeenCalledWith("clip-1"));
    expect(onApprove).toHaveBeenCalledWith("clip-1", true);
  });

  it("hands a rendered clip off to the separate publishing workspace", () => {
    render(
      <FinalExportPanel
        clip={{ ...clip, final_path: "/clips/clip-1/final.mp4" }}
        publishHref="/projects/project-1/clips/clip-1/publish"
        hasUnsavedChanges={false}
        approvalPending={false}
        onApprove={vi.fn().mockResolvedValue(true)}
        onRender={vi.fn()}
      />,
    );

    expect(
      screen
        .getByRole("link", { name: /Continue to publishing/ })
        .getAttribute("href"),
    ).toBe("/projects/project-1/clips/clip-1/publish");
  });
});

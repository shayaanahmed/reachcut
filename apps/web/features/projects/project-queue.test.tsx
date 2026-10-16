import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { projectSchema } from "../../lib/contracts";
import { ProjectQueue } from "./project-queue";

function project(id: string, status: string, date: string) {
  return projectSchema.parse({
    id,
    title: id,
    status,
    original_filename: "source.mp4",
    duration_seconds: null,
    authorization_confirmed_at: date,
    created_at: date,
    stages: [],
    clips: [],
    job: {
      status,
      phase: "Waiting to start",
      source_url: null,
      error: status === "failed" ? "Model unavailable" : null,
      enqueued_at: date,
    },
  });
}

describe("project queue", () => {
  it("shows FIFO positions, failures and actions while a project runs", () => {
    const cancel = vi.fn();
    const retry = vi.fn();
    render(
      <ProjectQueue
        projects={[
          project("second", "queued", "2026-10-15T10:02:00Z"),
          project("first", "queued", "2026-10-15T10:01:00Z"),
          project("running", "downloading", "2026-10-15T10:00:00Z"),
          project("failed", "failed", "2026-10-15T09:00:00Z"),
        ]}
        onCancel={cancel}
        onRetry={retry}
      />,
    );
    expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual(
      ["running", "first", "second", "failed"],
    );
    expect(
      screen.getByLabelText("Queue position 1").closest("li")?.textContent,
    ).toContain("first");
    expect(screen.getByText("Downloading video")).toBeTruthy();
    expect(screen.getByText("Model unavailable")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Pause second" }));
    fireEvent.click(screen.getByRole("button", { name: "Retry failed" }));
    expect(cancel).toHaveBeenCalledWith("second");
    expect(retry).toHaveBeenCalledWith("failed");
  });
});

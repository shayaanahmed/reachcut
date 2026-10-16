import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { projectSchema } from "../../lib/contracts";
import { ProjectCard } from "./project-card";

vi.mock("../publishing/project-performance", () => ({
  ProjectPerformance: () => null,
}));
afterEach(cleanup);

function setup(status: string, pending?: string) {
  const project = projectSchema.parse({
    id: "project-1",
    title: "Interview",
    status,
    original_filename: "source.mp4",
    duration_seconds: null,
    authorization_confirmed_at: "2026-10-16T10:00:00Z",
    created_at: "2026-10-16T10:00:00Z",
    stages: [],
    clips: [],
  });
  const actions = {
    onProcess: vi.fn(),
    onStop: vi.fn(),
    onRetry: vi.fn(),
    onApprove: vi.fn(),
    onDeleteClip: vi.fn(),
    onRender: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn(),
  };
  render(
    <ProjectCard
      project={project}
      language=""
      selectedClipTypes={[]}
      clipTypeSuggestions={[]}
      setLanguages={vi.fn()}
      setClipTypes={vi.fn()}
      isPending={(key) => key === `project:project-1:${pending}`}
      operationState={() => undefined}
      {...actions}
    />,
  );
  return actions;
}

describe("pipeline controls", () => {
  it("starts a new pipeline", () => {
    const actions = setup("created");
    fireEvent.click(screen.getByRole("button", { name: "Start pipeline" }));
    expect(actions.onProcess).toHaveBeenCalledWith("project-1");
  });
  it("pauses active work", () => {
    const actions = setup("processing");
    fireEvent.click(screen.getByRole("button", { name: "Pause pipeline" }));
    expect(actions.onStop).toHaveBeenCalledWith("project-1");
  });
  it("resumes paused work with saved inputs", () => {
    const actions = setup("cancelled");
    fireEvent.click(screen.getByRole("button", { name: "Resume pipeline" }));
    expect(actions.onRetry).toHaveBeenCalledWith("project-1");
    expect(actions.onProcess).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Spoken language")).toBeNull();
  });
  it("disables the action while pause is being acknowledged", () => {
    setup("cancel_requested");
    expect(
      (screen.getByRole("button", { name: "Pausing…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      screen.getByText(/Waiting for the current operation to stop safely/),
    ).toBeTruthy();
  });
  it("shows feedback while resuming", () => {
    setup("cancelled", "retry");
    expect(
      (screen.getByRole("button", { name: "Starting…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});

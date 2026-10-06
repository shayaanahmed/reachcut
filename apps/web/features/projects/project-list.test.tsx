import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { projectSchema, type Project } from "../../lib/contracts";
import { ProjectList } from "./project-list";

function project(id: string, title: string, status: Project["status"]) {
  return projectSchema.parse({
    id,
    title,
    original_filename: `${title.toLowerCase()}.mp4`,
    status,
    duration_seconds: 60,
    authorization_confirmed_at: "2026-10-02T10:00:00Z",
    created_at:
      id === "project-1" ? "2026-10-02T10:00:00Z" : "2026-10-03T10:00:00Z",
    stages: [],
    clips: [],
  });
}

describe("project list", () => {
  it("supports quick search, workflow filters, and a compact list view", () => {
    render(
      <ProjectList
        projects={[
          project("project-1", "Alpha Interview", "review"),
          project("project-2", "Beta Tutorial", "processing"),
        ]}
        isPending={() => false}
        onDelete={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Search projects"), {
      target: { value: "Alpha" },
    });
    expect(screen.getByText("Alpha Interview")).toBeTruthy();
    expect(screen.queryByText("Beta Tutorial")).toBeNull();

    fireEvent.change(screen.getByLabelText("Search projects"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "review" }));
    expect(screen.getByText("Alpha Interview")).toBeTruthy();
    expect(screen.queryByText("Beta Tutorial")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "List view" }));
    expect(
      screen
        .getByRole("button", { name: "List view" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
  });
});

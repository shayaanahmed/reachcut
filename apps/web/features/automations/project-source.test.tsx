import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { projectSchema } from "../../lib/contracts";
import { importProjectUrl, uploadProject } from "../projects/api";
import { ProjectSource } from "./project-source";

vi.mock("../projects/api", () => ({
  importProjectUrl: vi.fn(),
  uploadProject: vi.fn(),
}));
const project = projectSchema.parse({
  id: "new-project",
  title: "Interview",
  original_filename: "Pending URL import",
  status: "queued",
  duration_seconds: null,
  authorization_confirmed_at: "2026-10-15T10:00:00Z",
  created_at: "2026-10-15T10:00:00Z",
  stages: [],
  clips: [],
});

afterEach(cleanup);

beforeEach(() => {
  vi.resetAllMocks();
});

describe("automation source", () => {
  it("creates a queued project from a URL and selects it without leaving the builder", async () => {
    vi.mocked(importProjectUrl).mockResolvedValue(project);
    const onCreated = vi.fn();
    render(
      <ProjectSource
        projects={[]}
        selectedId=""
        onSelect={vi.fn()}
        onCreated={onCreated}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "From URL" }));
    fireEvent.change(screen.getByLabelText("Public video URL"), {
      target: { value: "https://youtube.com/watch?v=123" },
    });
    fireEvent.change(screen.getByLabelText("Source video name"), {
      target: { value: "Interview" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.submit(
      screen
        .getByRole("button", { name: "Add source video to queue" })
        .closest("form")!,
    );
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(project));
    expect(importProjectUrl).toHaveBeenCalledWith({
      title: "Interview",
      url: "https://youtube.com/watch?v=123",
      authorization_confirmed: true,
    });
    expect(screen.getByRole("status").textContent).toContain(
      "added to the processing queue",
    );
  });

  it("keeps the form available when importing fails", async () => {
    vi.mocked(importProjectUrl).mockRejectedValue(
      new Error("Unsupported video host"),
    );
    render(
      <ProjectSource
        projects={[]}
        selectedId=""
        onSelect={vi.fn()}
        onCreated={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "From URL" }));
    fireEvent.change(screen.getByLabelText("Public video URL"), {
      target: { value: "https://example.com/video" },
    });
    fireEvent.change(screen.getByLabelText("Source video name"), {
      target: { value: "Interview" },
    });
    fireEvent.submit(
      screen
        .getByRole("button", { name: "Add source video to queue" })
        .closest("form")!,
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Unsupported video host",
    );
    expect(
      (screen.getByLabelText("Source video name") as HTMLInputElement).value,
    ).toBe("Interview");
  });

  it("uploads a video and reports transfer progress", async () => {
    vi.mocked(uploadProject).mockImplementation(async (_data, onProgress) => {
      onProgress?.(50);
      return project;
    });
    const onCreated = vi.fn();
    render(
      <ProjectSource
        projects={[]}
        selectedId=""
        onSelect={vi.fn()}
        onCreated={onCreated}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Upload video" }));
    fireEvent.change(screen.getByLabelText("Source video file"), {
      target: {
        files: [new File(["media"], "interview.mp4", { type: "video/mp4" })],
      },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.submit(
      screen
        .getByRole("button", { name: "Add source video to queue" })
        .closest("form")!,
    );
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(project));
    expect(uploadProject).toHaveBeenCalledOnce();
  });
});

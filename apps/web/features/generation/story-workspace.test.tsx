import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StoryWorkspace } from "./story-workspace";

const api = vi.hoisted(() => ({
  getGeneratedVideo: vi.fn(),
  stopGeneratedVideo: vi.fn(),
  renameGeneratedVideo: vi.fn(),
  prepareStoryPublishing: vi.fn(),
  deleteGeneratedVideo: vi.fn(),
  resumeGeneratedVideo: vi.fn(),
}));
const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("./api", () => ({ ...api, generatedVideoUrl: () => "/master.mp4" }));
const video = {
  id: "short-1",
  status: "complete",
  plan: {
    title: "The lantern",
    logline: "A courier lights the city",
    characters: [],
    visual_style: "anime",
  },
  story: "A courier carries the city's last light.",
  aspect_ratio: "9:16",
  quality: "draft",
  progress: 1,
  target_duration_seconds: 10,
  provider: "local",
  scenes: [],
  error: null,
};

describe("Short management", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });
  it("stops a running project and enables deletion once stopped", async () => {
    api.getGeneratedVideo.mockResolvedValue({ ...video, status: "rendering" });
    api.stopGeneratedVideo.mockResolvedValue({ ...video, status: "cancelled" });
    render(<StoryWorkspace videoId="short-1" />);
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    fireEvent.click(
      await screen.findByRole("button", { name: "Stop project" }),
    );
    await screen.findByRole("button", { name: "Delete" });
    expect(api.stopGeneratedVideo).toHaveBeenCalledWith("short-1");
  });

  it("renames a finished short and opens its existing social publishing workflow", async () => {
    api.getGeneratedVideo.mockResolvedValue(video);
    api.renameGeneratedVideo.mockResolvedValue({
      ...video,
      plan: { ...video.plan, title: "City lights" },
    });
    api.prepareStoryPublishing.mockResolvedValue({
      project_id: "publishing-project",
      clip_id: "publishing-clip",
    });
    render(<StoryWorkspace videoId="short-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Rename" }));
    fireEvent.change(screen.getByLabelText("Short title"), {
      target: { value: "City lights" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save title" }));
    expect(
      await screen.findByRole("heading", { name: "City lights" }),
    ).toBeTruthy();
    expect(api.renameGeneratedVideo).toHaveBeenCalledWith(
      "short-1",
      "City lights",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Share on social platforms" }),
    );
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(
        "/projects/publishing-project/clips/publishing-clip/publish",
      ),
    );
    expect(api.prepareStoryPublishing).toHaveBeenCalledWith("short-1");
  });
  it("reports publishing preparation failures without leaving the short", async () => {
    api.getGeneratedVideo.mockResolvedValue(video);
    api.prepareStoryPublishing.mockRejectedValue(
      new Error("Master unavailable"),
    );
    render(<StoryWorkspace videoId="short-1" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Share on social platforms" }),
    );
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Master unavailable",
    );
    expect(push).not.toHaveBeenCalled();
  });
});

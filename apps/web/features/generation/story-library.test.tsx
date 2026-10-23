import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { GeneratedVideo } from "../../lib/contracts";
import { StoryLibrary } from "./story-library";

const api = vi.hoisted(() => ({
  deleteGeneratedVideo: vi.fn(),
  listGeneratedVideos: vi.fn(),
  resumeGeneratedVideo: vi.fn(),
}));

vi.mock("./api", () => ({
  ...api,
  generatedVideoUrl: () => null,
}));

const failedStory: GeneratedVideo = {
  id: "story-1",
  story:
    "An astronaut discovers an ancient garden beneath the surface of Mars.",
  template: "cinematic_story",
  aspect_ratio: "9:16",
  quality: "draft",
  target_duration_seconds: 20,
  status: "failed",
  phase: "Generation stopped",
  progress: 0,
  provider: "ltx-2.5-fast-local",
  error: "Renderer stopped",
  created_at: "2026-10-13T14:00:00Z",
  updated_at: "2026-10-13T14:01:00Z",
  video_url: null,
  plan: {
    title: "The garden beneath Mars",
    logline: "An astronaut follows a dormant robot to a hidden alien garden.",
    visual_style:
      "cinematic live-action film with natural texture and motivated light",
    negative_prompt: "identity drift, flicker, text, logos, anatomy errors",
    characters: [],
    scenes: [
      {
        index: 1,
        title: "Discovery",
        story_beat: "The astronaut discovers a dormant robot.",
        narration: "",
        visual_prompt:
          "A dust-covered astronaut uncovers a dormant robot in red Martian soil at sunrise.",
        character_ids: [],
        camera_motion: "none",
        duration_seconds: 5,
        seed: 12345,
      },
    ],
  },
  scenes: [
    {
      id: "scene-1",
      scene_index: 1,
      title: "Discovery",
      prompt: "A dust-covered astronaut uncovers a dormant robot.",
      narration: "",
      duration_seconds: 5,
      seed: 12345,
      status: "failed",
      progress: 0.05,
      error: "Renderer stopped",
    },
  ],
};

describe("AI scene video library", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("lists and resumes a failed story project", async () => {
    api.listGeneratedVideos.mockResolvedValue([failedStory]);
    api.resumeGeneratedVideo.mockResolvedValue({
      ...failedStory,
      status: "queued",
      phase: "Waiting for the local renderer",
      error: null,
    });

    render(<StoryLibrary />);

    expect(await screen.findByText("The garden beneath Mars")).toBeTruthy();
    const summary = within(screen.getByLabelText("AI scene video summary"));
    expect(summary.getByText("Needs attention").nextSibling?.textContent).toBe(
      "1",
    );
    fireEvent.click(screen.getByRole("button", { name: "Resume scene 1" }));

    await waitFor(() =>
      expect(api.resumeGeneratedVideo).toHaveBeenCalledWith("story-1"),
    );
    expect(
      await screen.findByText("Waiting for the local renderer"),
    ).toBeTruthy();
  });
});

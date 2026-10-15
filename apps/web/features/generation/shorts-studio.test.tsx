import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShortsStudio } from "./shorts-studio";
import {
  listReferenceTemplates,
  resolveReferenceTemplate,
} from "./template-library-api";

const api = vi.hoisted(() => ({
  authorizeHuggingFace: vi.fn(),
  createStoryIdea: vi.fn(),
  downloadVideoModels: vi.fn(),
  generateVideo: vi.fn(),
  getGeneratedVideo: vi.fn(),
  getVideoReadiness: vi.fn(),
  listGeneratedVideos: vi.fn(),
  listVideoTemplates: vi.fn(),
  listStoryDrafts: vi.fn().mockResolvedValue([]),
  saveStoryDraft: vi.fn(),
  deleteStoryDraft: vi.fn(),
  matchStoryFormat: vi.fn().mockResolvedValue({
    template: "cinematic_story",
    reference_template_id: null,
    reason: "Cinematic pacing fits the story",
  }),
  planStory: vi.fn(),
  resumeGeneratedVideo: vi.fn(),
  startVideoEngine: vi.fn(),
  uploadStoryReference: vi.fn(),
}));

vi.mock("./template-library-api", () => ({
  listReferenceTemplates: vi.fn().mockResolvedValue([]),
  referenceVideoUrl: () => undefined,
  referencePosterUrl: () => undefined,
  resolveReferenceTemplate: vi.fn().mockResolvedValue(null),
}));

vi.mock("./api", () => ({
  ...api,
  generatedVideoUrl: (video: { video_url: string | null }) => video.video_url,
}));

const formats = [
  {
    id: "cinematic_story" as const,
    name: "Cinematic story",
    description: "A live-action character film.",
    category: "Realistic",
    prompt_hint: "Describe the characters and ending.",
    style_prompt: "cinematic live-action film",
    palette: ["0B1021", "6D43FF", "E9D5FF"] as [string, string, string],
    badge: "CINEMA",
  },
  {
    id: "anime_story" as const,
    name: "Anime story",
    description: "Emotional anime pacing.",
    category: "Animation",
    prompt_hint: "Describe the conflict and final beat.",
    style_prompt: "high-end cinematic anime",
    palette: ["21103B", "F044A7", "9DEBFF"] as [string, string, string],
    badge: "ANIME",
  },
];

const plan = {
  title: "The lantern runner",
  logline: "A courier protects the final lantern through a storm.",
  visual_style: "high-end cinematic anime",
  negative_prompt: "identity drift, flicker, text, logos, anatomy errors",
  characters: [
    {
      id: "aya",
      name: "Aya",
      role: "courier",
      appearance_anchor:
        "young woman with an oval face, amber eyes and black bobbed hair",
      wardrobe_anchor: "red rain cape, charcoal trousers and black boots",
      voice_anchor: "steady young alto",
    },
  ],
  scenes: [
    {
      index: 1,
      title: "The storm",
      story_beat: "Aya runs into the storm with the final lantern.",
      narration: "One light was still alive.",
      visual_prompt:
        "Aya runs along a rain-covered bridge holding a warm lantern as the camera advances.",
      character_ids: ["aya"],
      camera_motion: "dolly_in" as const,
      duration_seconds: 5 as const,
      seed: 801,
    },
    {
      index: 2,
      title: "The return",
      story_beat: "The lantern relights the sleeping city.",
      narration: "Then the city remembered dawn.",
      visual_prompt:
        "Aya raises the lantern in the central square and windows illuminate around her.",
      character_ids: ["aya"],
      camera_motion: "jib_up" as const,
      duration_seconds: 5 as const,
      seed: 802,
    },
  ],
};

const ready = {
  ready: true,
  ollama_connected: true,
  ollama_model_ready: true,
  engine_installed: true,
  engine_running: true,
  models_ready: true,
  hf_authenticated: true,
  download_status: "idle",
  download_progress: 0,
  engine_name: "LTX 2.5 Fast · Apple Silicon",
  detail: "Ready",
};

describe("Story Studio", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.mocked(resolveReferenceTemplate).mockResolvedValue(null);
    vi.mocked(listReferenceTemplates).mockResolvedValue([]);
    api.listStoryDrafts.mockResolvedValue([]);
  });

  it("requires a storyboard before submitting a local character render", async () => {
    api.listVideoTemplates.mockResolvedValue(formats);
    api.listGeneratedVideos.mockResolvedValue([]);
    api.getVideoReadiness.mockResolvedValue(ready);
    api.planStory.mockResolvedValue(plan);
    api.generateVideo.mockResolvedValue({
      id: "story-1",
      story:
        "A courier carries the final lantern through a storm to wake her city.",
      template: "anime_story",
      aspect_ratio: "9:16",
      quality: "draft",
      target_duration_seconds: 10,
      status: "queued",
      phase: "Waiting for the local renderer",
      progress: 0,
      plan,
      provider: "ltx-2.5-fast-local",
      error: null,
      created_at: "2026-10-13T10:00:00Z",
      updated_at: "2026-10-13T10:00:00Z",
      scenes: [],
      video_url: null,
    });

    render(<ShortsStudio />);
    await screen.findByText("Optional visual style");
    fireEvent.click(screen.getByText("Optional visual style"));
    await screen.findByRole("button", { name: /Anime story/ });
    fireEvent.click(screen.getByRole("button", { name: /Anime story/ }));
    fireEvent.change(screen.getByLabelText("Story"), {
      target: {
        value:
          "A courier carries the final lantern through a storm to wake her city.",
      },
    });
    fireEvent.change(screen.getByLabelText("Story length"), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByText("Review a storyboard before creating"));
    fireEvent.click(screen.getByRole("button", { name: "Create storyboard" }));

    expect(await screen.findByText("The lantern runner")).toBeTruthy();
    expect(api.planStory).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        template: "anime_story",
        visual_style_override: true,
      }),
      10,
      expect.any(AbortSignal),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Generate draft story video" }),
    );

    await waitFor(() =>
      expect(api.generateVideo).toHaveBeenCalledWith({
        story:
          "A courier carries the final lantern through a storm to wake her city.",
        plan,
        template: "anime_story",
        aspect_ratio: "9:16",
        quality: "draft",
      }),
    );
  });

  it("turns a rough idea into a full story with Ollama", async () => {
    api.listVideoTemplates.mockResolvedValue(formats);
    api.listGeneratedVideos.mockResolvedValue([]);
    api.getVideoReadiness.mockResolvedValue(ready);
    api.createStoryIdea.mockResolvedValue({
      hook: "The last lantern is moving.",
      story:
        "A courier finds the final lantern and crosses a flooded city to return dawn.",
    });

    render(<ShortsStudio />);
    await screen.findByText("Optional visual style");
    fireEvent.change(screen.getByLabelText("Story"), {
      target: { value: "last lantern" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Turn my idea into a viral story" }),
    );

    await waitFor(() =>
      expect(screen.getByLabelText("Story")).toHaveProperty(
        "value",
        "A courier finds the final lantern and crosses a flooded city to return dawn.",
      ),
    );
  });
  it("passes the automatically selected reference into storyboard direction", async () => {
    api.listVideoTemplates.mockResolvedValue(formats);
    api.listGeneratedVideos.mockResolvedValue([]);
    api.getVideoReadiness.mockResolvedValue(ready);
    api.planStory.mockResolvedValue(plan);
    const referenceId = "a".repeat(32);
    vi.mocked(listReferenceTemplates).mockResolvedValue([
      {
        id: referenceId,
        name: "Anime chase",
        status: "ready",
        source_url: null,
        source_category: null,
        video_url: null,
        poster_url: null,
        error: null,
        analysis_model: "vision",
        duration_seconds: 10,
        blueprint: {
          name: "Anime chase",
          base_template: "anime_story",
          format: "anime",
          tags: ["chase"],
          visual_style: "Cinematic anime",
          camera: "Dynamic tracking",
          pacing: "Urgent escalation",
          story_structure: "Pursuit and escape",
          caption_style: "None",
          suitable_for: "Chase stories",
        },
      },
    ]);
    vi.mocked(resolveReferenceTemplate).mockResolvedValue({
      template: "anime_story",
      reference_template_id: referenceId,
      reason: "Anime suits the chase",
    });
    render(<ShortsStudio />);
    await screen.findByText("Optional visual style");
    await screen.findByRole("button", { name: "Use template" });
    api.matchStoryFormat.mockResolvedValue({
      template: "anime_story",
      reference_template_id: referenceId,
      reason: "Anime suits the chase",
    });
    const story =
      "A courier races across a flooded city carrying its last lantern.";
    fireEvent.change(screen.getByLabelText("Story"), {
      target: { value: story },
    });
    fireEvent.click(screen.getByText("Review a storyboard before creating"));
    fireEvent.click(screen.getByRole("button", { name: "Create storyboard" }));
    await screen.findByText("The lantern runner");
    expect(api.matchStoryFormat).toHaveBeenCalledWith(
      story,
      expect.any(AbortSignal),
    );
    expect(api.planStory).toHaveBeenCalledWith(
      story,
      {
        template: "anime_story",
        aspect_ratio: "9:16",
        reference_template_id: referenceId,
      },
      10,
      expect.any(AbortSignal),
    );
    expect(
      screen.getByText("Template match: Anime suits the chase"),
    ).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Story length"), {
      target: { value: "30" },
    });
    expect(screen.queryByText("The lantern runner")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Use template" }));
    fireEvent.click(screen.getByRole("button", { name: "Create storyboard" }));
    await screen.findByText("The lantern runner");
    expect(resolveReferenceTemplate).toHaveBeenCalledWith(referenceId, story);
    expect(api.planStory).toHaveBeenLastCalledWith(
      story,
      {
        template: "anime_story",
        aspect_ratio: "9:16",
        reference_template_id: referenceId,
      },
      30,
      expect.any(AbortSignal),
    );
    expect(
      screen.getByRole("button", { name: "Selected template" }),
    ).toBeTruthy();
  });
});

const storyText =
  "A courier carries the final lantern through a storm to wake her city.";
const draftSettings = {
  story: storyText,
  template: null,
  aspect_ratio: "9:16",
  quality: "draft",
  target_duration_seconds: 10,
};
const queuedDraft = {
  id: "draft-1",
  story: storyText,
  settings: draftSettings,
  created_at: "2026-10-14T10:00:00Z",
};
const queuedVideo = {
  id: "video-1",
  story: storyText,
  template: "anime_story",
  aspect_ratio: "9:16",
  quality: "draft",
  target_duration_seconds: 10,
  status: "queued",
  phase: "Waiting for renderer",
  progress: 0,
  plan,
  provider: "local",
  error: null,
  created_at: "2026-10-14T10:00:00Z",
  scenes: [],
  video_url: null,
};

function prepareStudio() {
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  api.listVideoTemplates.mockResolvedValue(formats);
  api.listGeneratedVideos.mockResolvedValue([]);
  api.getVideoReadiness.mockResolvedValue(ready);
  api.listStoryDrafts.mockResolvedValue([]);
  api.matchStoryFormat.mockResolvedValue({
    template: "anime_story",
    reference_template_id: null,
    reason: "Anime suits the chase",
  });
  api.planStory.mockResolvedValue(plan);
  api.generateVideo.mockResolvedValue(queuedVideo);
  vi.mocked(listReferenceTemplates).mockResolvedValue([]);
  vi.mocked(resolveReferenceTemplate).mockResolvedValue(null);
}

describe("Shorts creation and manual queue", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("automatically classifies a story and creates a short without requiring storyboard review", async () => {
    prepareStudio();
    render(<ShortsStudio />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Create short" }),
      ).toBeEnabled(),
    );
    fireEvent.change(screen.getByLabelText("Story"), {
      target: { value: storyText },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create short" }));
    await waitFor(() =>
      expect(api.generateVideo).toHaveBeenCalledWith(
        expect.objectContaining({
          story: storyText,
          template: "anime_story",
          plan,
        }),
      ),
    );
    expect(api.matchStoryFormat).toHaveBeenCalledWith(
      storyText,
      expect.any(AbortSignal),
    );
    expect(screen.getByRole("button", { name: "Create short" })).toBeDisabled();
  });

  it("saves stories without generating, restores the queue and starts only the first item", async () => {
    prepareStudio();
    api.listStoryDrafts.mockResolvedValue([
      queuedDraft,
      { ...queuedDraft, id: "draft-2", story: "A second saved story" },
    ]);
    render(<ShortsStudio />);
    await screen.findByText("Story queue (2)");
    expect(api.generateVideo).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Start next short" }));
    await waitFor(() =>
      expect(api.generateVideo).toHaveBeenCalledWith(
        expect.objectContaining({ draft_id: "draft-1" }),
      ),
    );
    expect(await screen.findByText("Story queue (1)")).toBeTruthy();
    expect(api.generateVideo).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("button", { name: "Start next short" }),
    ).toBeDisabled();
  });

  it("retains a queued story when planning fails and allows a manual retry", async () => {
    prepareStudio();
    api.listStoryDrafts.mockResolvedValue([queuedDraft]);
    api.planStory.mockRejectedValue(new Error("Planner unavailable"));
    render(<ShortsStudio />);
    await screen.findByText("Story queue (1)");
    fireEvent.click(screen.getByRole("button", { name: "Start next short" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Planner unavailable",
    );
    expect(screen.getByText("Story queue (1)")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Start next short" }),
    ).toBeEnabled();
    expect(api.generateVideo).not.toHaveBeenCalled();
  });

  it("stops creation during format selection without starting a video", async () => {
    prepareStudio();
    let finishMatch!: (value: {
      template: string;
      reference_template_id: null;
      reason: string;
    }) => void;
    api.matchStoryFormat.mockReturnValue(
      new Promise((resolve) => {
        finishMatch = resolve;
      }),
    );
    render(<ShortsStudio />);
    await screen.findByRole("button", { name: "Create short" });
    fireEvent.change(screen.getByLabelText("Story"), {
      target: { value: storyText },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create short" }));
    await waitFor(() => expect(api.matchStoryFormat).toHaveBeenCalled());
    fireEvent.click(
      screen.getByRole("button", { name: "Stop story creation" }),
    );
    expect(api.matchStoryFormat.mock.calls[0][1].aborted).toBe(true);
    finishMatch({
      template: "anime_story",
      reference_template_id: null,
      reason: "Matched",
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Create short" }),
      ).toBeEnabled(),
    );
    expect(api.planStory).not.toHaveBeenCalled();
    expect(api.generateVideo).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Story")).toHaveValue(storyText);
  });

  it("lets users edit queued stories and save their selected format", async () => {
    prepareStudio();
    api.listStoryDrafts.mockResolvedValue([queuedDraft]);
    api.saveStoryDraft.mockResolvedValue({
      ...queuedDraft,
      story: `${storyText} A new ending.`,
    });
    render(<ShortsStudio />);
    await screen.findByText("Story queue (1)");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Story"), {
      target: { value: `${storyText} A new ending.` },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save queued story" }));
    await waitFor(() =>
      expect(api.saveStoryDraft).toHaveBeenCalledWith(
        expect.objectContaining({
          story: `${storyText} A new ending.`,
          template: null,
        }),
        "draft-1",
      ),
    );
    expect(api.generateVideo).not.toHaveBeenCalled();
  });
});

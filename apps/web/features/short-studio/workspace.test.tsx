import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShortStudio } from "./workspace";
import { defaultSelection } from "./frame-picker";
import { FrameLibrary } from "./frame-library";
import { studioApi } from "./api";
import type { StudioBrief, StudioJob, FrameSequence } from "./api";
import { request } from "../informative/api";

vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  studioApi: {
    ideas: vi.fn(),
    storyboard: vi.fn(),
    job: vi.fn(),
    brief: vi.fn(),
    frames: vi.fn(),
    sequences: vi.fn(),
    episode: vi.fn(),
  },
}));
vi.mock("../informative/api", async (original) => ({
  ...(await original<typeof import("../informative/api")>()),
  request: vi.fn(),
}));
vi.mock("../content-series/episode-review", () => ({
  EpisodeReview: () => <h2>Storyboard ready for review</h2>,
}));
const brief: StudioBrief = {
  id: "brief-1",
  category: "github",
  subject: "example/photos",
  repo_url: "https://github.com/example/photos",
  context: "",
  analysis: "This repository organizes photographs by date.",
  sources: [],
  notices: [],
  storylines: [1, 2, 3].map((i) => ({
    id: `story-${i}`,
    title: `A useful photo story ${i}`,
    hook: "Where did that holiday photo go?",
    focus: "A messy folder becomes easier to navigate.",
    payoff: "You could organize your photographs.",
    source_id: "docs",
  })),
};
const sequence: FrameSequence = {
  id: "vol3-editorial",
  name: "Vol. 3 · Editorial",
  description: "Six different scenes.",
  background: "#FFF6E8",
  accent: "#244FF5",
  secondary: "#FF567E",
  font: "Bricolage Grotesque",
  frames: [
    "kinetic-poster",
    "newspaper",
    "chat-thread",
    "receipt",
    "sticker-pack",
    "story-poll",
  ],
  durations: [3, 4, 4, 7, 7, 5],
};
const ready: StudioJob = {
  id: "ideas-job",
  kind: "ideas",
  status: "ready",
  phase: "Choose a storyline",
  error: "",
  brief,
  short_id: "",
  ideas_request: {
    category: "github",
    repo_url: brief.repo_url,
    context: "",
    previous_brief_id: "",
    request_key: "stable-request",
  },
  storyboard_request: null,
};
beforeEach(() => {
  vi.clearAllMocks();
  const memory = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => memory.get(key) ?? null,
      setItem: (key: string, value: string) => memory.set(key, value),
      removeItem: (key: string) => memory.delete(key),
      clear: () => memory.clear(),
    },
  });
  window.history.replaceState(null, "", "/create");
  vi.mocked(request).mockResolvedValue({
    narration: { connected: false, profiles: [], engines: [] },
  });
  vi.mocked(studioApi.sequences).mockResolvedValue([sequence]);
  vi.mocked(studioApi.frames).mockResolvedValue([]);
  vi.mocked(studioApi.ideas).mockResolvedValue(ready);
  vi.mocked(studioApi.job).mockResolvedValue(ready);
});
afterEach(cleanup);
describe("simple short studio", () => {
  it("keeps inputs and navigation usable while ideas run without duplicate jobs", async () => {
    vi.mocked(studioApi.job).mockResolvedValue({
      ...ready,
      status: "working",
      brief: null,
      phase: "Reading sources",
    });
    render(<ShortStudio />);
    fireEvent.change(screen.getByLabelText("Public GitHub repo URL"), {
      target: { value: brief.repo_url },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Generate AI storyboard/ }),
    );
    await screen.findByText("Reading sources");
    expect(screen.getByLabelText("Public GitHub repo URL")).toBeEnabled();
    expect(
      screen.getByRole("link", { name: "Frame library" }),
    ).toBeInTheDocument();
    const running = screen.getByRole("button", {
      name: /Writing your storyboard/,
    });
    expect(running).toBeEnabled();
    fireEvent.click(running);
    expect(studioApi.ideas).toHaveBeenCalledTimes(1);
  });
  it("keeps frame previews interactive while a storyboard is building", async () => {
    window.localStorage.setItem("reachcut-studio-job", "plan-job");
    vi.mocked(studioApi.job).mockResolvedValue({
      ...ready,
      kind: "storyboard",
      status: "working",
      phase: "Designing and checking scene 2 of 6",
      storyboard_request: {
        brief_id: brief.id,
        storyline_id: "story-1",
        sequence_id: sequence.id,
        request_key: "plan-request",
        feedback: "",
        frame_mode: "manual",
        frames: sequence.frames,
      },
    });
    render(<ShortStudio />);
    await screen.findByRole("heading", { name: "Choose your frames" });
    fireEvent.click(screen.getByRole("button", { name: "Scene 3: Example" }));
    expect(
      screen.getByRole("button", { name: "Scene 3: Example" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTitle("Preview: chat-thread")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Replay preview/ }),
    ).toBeEnabled();
    fireEvent.click(
      screen.getByRole("button", { name: /Building storyboard/ }),
    );
    expect(studioApi.storyboard).not.toHaveBeenCalled();
  });

  it("accepts only a repo URL and goes from story to selected frames", async () => {
    vi.mocked(studioApi.sequences).mockResolvedValue([
      {
        ...sequence,
        id: defaultSelection.sequence,
        frames: defaultSelection.frames,
      },
    ]);
    render(<ShortStudio />);
    expect(screen.queryByText("New niche")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Public GitHub repo URL"), {
      target: { value: brief.repo_url },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Generate AI storyboard/ }),
    );
    await screen.findByRole("heading", {
      name: "Which story would you watch?",
    });
    expect(studioApi.ideas).toHaveBeenCalledWith(
      expect.objectContaining({
        repo_url: brief.repo_url,
        category: "github",
        context: "",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /A useful photo story 1/ }),
    );
    await screen.findByRole("heading", { name: "Choose your frames" });
    expect(
      screen.getByRole("button", { name: /Let AI choose/ }),
    ).toHaveAttribute("aria-pressed", "true");
    vi.mocked(studioApi.storyboard).mockResolvedValue({
      ...ready,
      id: "plan-job",
      kind: "storyboard",
      short_id: "short-1",
      storyboard_request: {
        brief_id: brief.id,
        storyline_id: "story-1",
        sequence_id: "vol3-editorial",
        request_key: "plan-request",
        feedback: "",
      },
    });
    vi.mocked(studioApi.job).mockResolvedValue({
      ...ready,
      id: "plan-job",
      kind: "storyboard",
      short_id: "short-1",
    });
    vi.mocked(studioApi.episode).mockResolvedValue({
      short: { id: "short-1" },
    } as Awaited<ReturnType<typeof studioApi.episode>>);
    fireEvent.click(
      screen.getByRole("button", { name: "Build my storyboard →" }),
    );
    await screen.findByRole("heading", { name: "Storyboard ready for review" });
    expect(studioApi.storyboard).toHaveBeenCalledWith(
      expect.objectContaining({
        brief_id: brief.id,
        storyline_id: "story-1",
        sequence_id: defaultSelection.sequence,
        frame_mode: "ai",
      }),
    );
  });
  it("shows the GitHub storyboard before templates and creates a reviewed video", async () => {
    const storyBrief: StudioBrief = {
      ...brief,
      storyboard_storyline_id: "story-1",
      storyboard: [1, 2, 3, 4, 5].map((index) => ({
        narration: `Approved narration for scene ${index}.`,
        caption: `Caption ${index}`,
        title: `Scene ${index}`,
        visual: "Photos move into dated folders",
        excerpt_id: "E1",
        choices: [],
      })),
    };
    const draftJob = { ...ready, brief: storyBrief };
    vi.mocked(studioApi.ideas).mockResolvedValue(draftJob);
    vi.mocked(studioApi.job).mockResolvedValue(draftJob);
    vi.mocked(studioApi.sequences).mockResolvedValue([
      {
        ...sequence,
        frames: sequence.frames.slice(0, 5),
        durations: sequence.durations.slice(0, 5),
      },
    ]);
    render(<ShortStudio />);
    fireEvent.change(screen.getByLabelText("Public GitHub repo URL"), {
      target: { value: brief.repo_url },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Generate AI storyboard/ }),
    );
    await screen.findByRole("heading", { name: "Your repository storyboard" });
    expect(
      screen.getByText("Approved narration for scene 1."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Choose your template" }),
    ).not.toBeInTheDocument();
    expect(studioApi.ideas).toHaveBeenCalledWith(
      expect.objectContaining({ flow: "storyboard" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Use storyboard → choose template" }),
    );
    await screen.findByRole("heading", { name: "Choose your template" });
    fireEvent.click(
      await screen.findByRole("button", { name: "Use this template" }),
    );
    const videoJob = {
      ...draftJob,
      id: "video-plan",
      kind: "storyboard" as const,
      short_id: "video-1",
    };
    vi.mocked(studioApi.storyboard).mockResolvedValue(videoJob);
    vi.mocked(studioApi.job).mockResolvedValue(videoJob);
    vi.mocked(studioApi.episode).mockResolvedValue({
      short: { id: "video-1" },
    } as Awaited<ReturnType<typeof studioApi.episode>>);
    fireEvent.click(
      screen.getByRole("button", { name: "Create video with this template →" }),
    );
    await waitFor(() =>
      expect(studioApi.storyboard).toHaveBeenCalledWith(
        expect.objectContaining({
          brief_id: brief.id,
          storyline_id: "story-1",
          sequence_id: sequence.id,
          frame_mode: "manual",
          auto_produce: true,
        }),
      ),
    );
    expect(
      vi.mocked(studioApi.storyboard).mock.calls[0][0].frames,
    ).toBeUndefined();
  });
  it("can discover tech tricks with no mandatory topic input", async () => {
    render(<ShortStudio />);
    fireEvent.click(
      screen.getByRole("button", { name: /Tech tricks Let Ollama/ }),
    );
    expect(
      screen.queryByLabelText("Public GitHub repo URL"),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /Find exciting tech tricks/ }),
    );
    await waitFor(() =>
      expect(studioApi.ideas).toHaveBeenCalledWith(
        expect.objectContaining({
          category: "tech-tricks",
          repo_url: "",
          context: "",
        }),
      ),
    );
  });
  it("retries a failed task with the same request and polls it again", async () => {
    vi.mocked(studioApi.job).mockResolvedValueOnce({
      ...ready,
      status: "failed",
      brief: null,
      error: "Ollama offline",
    });
    render(<ShortStudio />);
    fireEvent.change(screen.getByLabelText("Public GitHub repo URL"), {
      target: { value: brief.repo_url },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Generate AI storyboard/ }),
    );
    await screen.findByText("Ollama offline");
    vi.mocked(studioApi.ideas).mockResolvedValue({
      ...ready,
      status: "queued",
      brief: null,
    });
    fireEvent.click(screen.getByRole("button", { name: "Retry saved task" }));
    await screen.findByRole("heading", {
      name: "Which story would you watch?",
    });
    expect(studioApi.ideas).toHaveBeenLastCalledWith(ready.ideas_request);
  });
  it("restores durable ideas after a reload", async () => {
    window.localStorage.setItem("reachcut-studio-job", "ideas-job");
    render(<ShortStudio />);
    await screen.findByRole("heading", {
      name: "Which story would you watch?",
    });
    expect(studioApi.job).toHaveBeenCalledWith("ideas-job");
  });
  it("keeps the supplied designs, filters collections and replays real frame previews", async () => {
    vi.mocked(studioApi.frames).mockResolvedValue([
      {
        id: "code-editor",
        volume: 3,
        name: "Code editor window",
        description: "Three typed lines of usage.",
        use: "Explain",
        sample: {
          template: "code-editor",
          caption: "Three lines",
          eyebrow: "Example",
          title: "Try this",
          items: [],
          query: "",
          duration_seconds: 5,
        },
      },
    ]);
    const { container } = render(<FrameLibrary />);
    await screen.findByRole("heading", { name: "Code editor window" });
    const player = screen.getByTitle("Code editor window");
    expect(player).toHaveAttribute(
      "src",
      expect.stringContaining("/short-studio/frames/code-editor/player"),
    );
    expect(player).toHaveAttribute("sandbox", "allow-scripts");
    fireEvent.click(screen.getByRole("button", { name: "Replay all frames" }));
    expect(screen.getByTitle("Code editor window")).not.toBe(player);
    expect(screen.queryByLabelText("Volume 2 theme")).not.toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Volume 3" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Collection"), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText("Find a frame"), {
      target: { value: "no match" },
    });
    expect(screen.getByRole("status")).toHaveTextContent("No frames match");
    fireEvent.change(screen.getByLabelText("Find a frame"), {
      target: { value: "typed" },
    });
    expect(screen.getByTitle("Code editor window")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Complete sequences" }));
    expect(container.querySelectorAll("iframe")).toHaveLength(6);
    expect(
      screen.getByRole("heading", { name: "Vol. 3 · Editorial" }),
    ).toBeInTheDocument();
  });
});

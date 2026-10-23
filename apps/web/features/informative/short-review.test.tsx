import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShortReview } from "./short-review";
import { defaults, request } from "./api";
import type { Short } from "./api";
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  request: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
const video: Short = {
  id: "short-1",
  topic: "AI workflow",
  settings: { ...defaults, narration_mode: "none" },
  sources: [],
  script: {
    version: "1",
    sections: [
      {
        id: "scene_1",
        heading: "Result",
        text: "Here is the result.",
        visual: "recording",
        claims: [],
      },
    ],
  },
  status: "review",
  phase: "Video ready",
  error: null,
  artifacts: {},
  approved: true,
  has_output: true,
  findings: [],
  script_issues: [],
  usage: {},
  publication_project_id: null,
};
describe("short review", () => {
  it("shows final AI scores and holds publishing when refinement is needed", () => {
    render(
      <ShortReview
        short={{
          ...video,
          final_review: {
            status: "needs_refinement",
            basis: "Sampled frames and script",
            assessment: {
              publishable: false,
              summary: "Scene 1 text is too small",
              hook_score: 70,
              clarity_score: 40,
              pacing_score: 75,
              shareability_score: 60,
              strengths: [],
              issues: [
                {
                  scene: 1,
                  severity: "blocking",
                  message: "Shorten the caption",
                },
              ],
            },
            history: [{ pass: 1 }, { pass: 2 }],
          },
        }}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "AI review needs attention" }),
    ).toBeTruthy();
    expect(screen.getByText("40/100")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Reviewed — open clip editor" }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: "Retry final review and refinement" }),
    ).toBeTruthy();
  });
  it("allows publishing review after the final AI assessment passes", () => {
    render(
      <ShortReview
        short={{
          ...video,
          final_review: {
            status: "passed",
            assessment: {
              publishable: true,
              summary: "A clear cut",
              hook_score: 85,
              clarity_score: 90,
              pacing_score: 80,
              shareability_score: 80,
              strengths: [],
              issues: [],
            },
          },
        }}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "AI review passed" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Reviewed — open clip editor" }),
    ).toBeTruthy();
  });
  it("adds VoiceBox narration only on request and reuses the existing short", async () => {
    vi.mocked(request).mockImplementation(async (path) =>
      path === "/shorts/providers"
        ? {
            narration: {
              connected: true,
              profiles: [{ id: "voice-1", name: "My voice" }],
              engines: [
                {
                  engine: "qwen",
                  model_name: "qwen-1.7B",
                  display_name: "Qwen 1.7B",
                  downloaded: true,
                  languages: ["en"],
                  supports_delivery: true,
                },
              ],
            },
          }
        : { ...video, status: path.endsWith("produce") ? "queued" : "draft" },
    );
    render(<ShortReview short={video} onChange={vi.fn()} />);
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Add or change voice-over" }),
    );
    await screen.findByRole("option", { name: "My voice" });
    fireEvent.change(screen.getByLabelText("VoiceBox voice"), {
      target: { value: "voice-1" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create narrated version" }),
    );
    await waitFor(() =>
      expect(request).toHaveBeenCalledWith("/shorts/short-1/produce", "POST"),
    );
    expect(request).toHaveBeenCalledWith(
      "/shorts/short-1/settings",
      "PUT",
      expect.objectContaining({
        profile_id: "voice-1",
        narration_mode: "voicebox",
      }),
    );
  });
});

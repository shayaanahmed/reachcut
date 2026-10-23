import { API_URL, responseError } from "../../lib/http";
import { request } from "../informative/api";
import type { Evidence } from "../informative/api";
import type { EpisodeDetail } from "../content-series/api";

export type Category = "github" | "tech-tricks";
export type FrameKind = string;
export type FrameContent = {
  template: FrameKind;
  caption: string;
  eyebrow: string;
  title: string;
  items: { title: string; body: string }[];
  query: string;
  duration_seconds: number;
};
export type FrameDefinition = {
  id: FrameKind;
  name: string;
  description: string;
  use: string;
  sample: FrameContent;
  volume?: number;
};
export type FrameSequence = {
  id: string;
  name: string;
  description: string;
  background: string;
  accent: string;
  secondary: string;
  font: string;
  frames: FrameKind[];
  durations: number[];
  theme?: string;
};
export type Storyline = {
  id: string;
  title: string;
  hook: string;
  focus: string;
  payoff: string;
  source_id: string;
  example?: string;
  prerequisite?: string;
  steps?: { title: string; body: string }[];
};
export type StudioBrief = {
  id: string;
  category: Category;
  subject: string;
  repo_url: string;
  context: string;
  analysis: string;
  sources: Evidence[];
  storylines: Storyline[];
  notices: string[];
  storyboard?: {
    narration: string;
    caption: string;
    title: string;
    visual: string;
    excerpt_id: string;
    choices: string[];
  }[];
  storyboard_storyline_id?: string;
  storyboard_notes?: string[];
};
export type IdeaInput = {
  flow?: "storylines" | "storyboard";
  category: Category;
  repo_url: string;
  context: string;
  previous_brief_id: string;
  request_key: string;
};
export type StoryboardInput = {
  auto_produce?: boolean;
  brief_id: string;
  storyline_id: string;
  sequence_id: string;
  request_key: string;
  feedback: string;
  theme?: string;
  frame_mode?: "ai" | "manual";
  frames?: FrameKind[];
  source_short_id?: string;
};
export type StudioJob = {
  id: string;
  kind: "ideas" | "storyboard";
  status: "queued" | "working" | "ready" | "failed";
  phase: string;
  error: string;
  brief: StudioBrief | null;
  short_id: string;
  ideas_request: IdeaInput | null;
  storyboard_request: StoryboardInput | null;
};
export const studioApi = {
  ideas: (input: IdeaInput) =>
    request<StudioJob>("/short-studio/ideas", "POST", input),
  storyboard: (input: StoryboardInput) =>
    request<StudioJob>("/short-studio/storyboards", "POST", input),
  job: (id: string) =>
    request<StudioJob>(`/short-studio/jobs/${encodeURIComponent(id)}`),
  brief: (id: string) =>
    request<StudioBrief>(`/short-studio/briefs/${encodeURIComponent(id)}`),
  importFrames: async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(`${API_URL}/short-studio/frames/import`, {
      method: "POST",
      body,
    });
    if (!response.ok)
      throw await responseError(response, "Could not import frames");
    return response.json() as Promise<{ frames: number; sequences: number }>;
  },
  frames: () => request<FrameDefinition[]>("/short-studio/frames"),
  sequences: () => request<FrameSequence[]>("/short-studio/sequences"),
  episode: (id: string) =>
    request<EpisodeDetail>(
      `/content-series/episodes/${encodeURIComponent(id)}`,
    ),
};
export const framePreviewUrl = (id: FrameKind, sequence?: string) =>
  `${API_URL}/short-studio/frames/${encodeURIComponent(id)}/preview${sequence ? `?sequence_id=${encodeURIComponent(sequence)}` : ""}`;
export const sequenceSampleUrl = (id: string, theme?: string) =>
  `${API_URL}/short-studio/sequences/${encodeURIComponent(id)}/sample.mp4${theme ? `?theme=${encodeURIComponent(theme)}` : ""}`;

export const framePlayerUrl = (
  id: FrameKind,
  sequence?: string,
  theme?: string,
) => {
  const params = new URLSearchParams();
  if (sequence) params.set("sequence_id", sequence);
  if (theme) params.set("theme", theme);
  return `${API_URL}/short-studio/frames/${encodeURIComponent(id)}/player${params.size ? `?${params}` : ""}`;
};

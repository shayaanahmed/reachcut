import { API_URL } from "../../lib/http";
import type {
  Evidence,
  Script,
  Short,
  ShortSettings,
  SocialReference,
} from "../informative/api";

export type ThumbnailDesign = {
  layout: "split" | "centered" | "terminal";
  background: string;
  accent: string;
  foreground: string;
  label: string;
  headline_template: string;
};
export type StyleBeat = {
  heading: string;
  visual: "source" | "code" | "diagram" | "recording";
  direction: string;
};
export type SeriesStyle = {
  frame_sequence?: import("../short-studio/api").FrameSequence | null;
  id: string;
  name: string;
  hook_template: string;
  pacing: string;
  caption_style: "clean" | "bold" | "minimal";
  beats: StyleBeat[];
  reference_ids: string[];
  basis: "starter" | "custom" | "reference-inspired";
  layout?: "poster" | "split" | "spotlight" | "kinetic" | "editorial" | "cards";
  design?: TemplateDesign | null;
};
export type TemplateDesign = {
  background: string;
  accent: string;
  foreground: string;
  font: string;
  weight: number;
  uppercase: boolean;
  background_prompt: string;
  background_asset_id: string;
  visual_direction: string;
  font_reason: string;
  niche_reason: string;
  suitable_for: string[];
  reuse_background: boolean;
  preview_scenes?: {
    heading: string;
    body: string;
    duration_seconds: number;
  }[];
};
export type FontLook = {
  name: string;
  font: string;
  weight: number;
  uppercase: boolean;
  reason: string;
};
export type DesignJob = {
  id: string;
  series_id: string;
  status: string;
  phase: string;
  styles: SeriesStyle[];
  error: string;
};
export type SeriesConfig = {
  name: string;
  purpose: string;
  audience: string;
  artwork_mode?: "designed" | "ollama";
  image_model?: string;
  headline_font?: string;
  active_template_id?: string;
  settings: ShortSettings;
  thumbnail: ThumbnailDesign;
};
export type ContentSeries = SeriesConfig & {
  id: string;
  styles: SeriesStyle[];
  references: SocialReference[];
  notices: string[];
  updated_at: string;
};
export type EpisodeAngle = {
  id: string;
  title: string;
  hook: string;
  focus: string;
};
export type EpisodeBrief = {
  id: string;
  series_id: string;
  subject: string;
  source_url: string;
  notes: string;
  sources: Evidence[];
  notices: string[];
  angles: EpisodeAngle[];
};
import type { FrameContent } from "../short-studio/api";

export type EpisodeVisual = {
  frame?: FrameContent | null;
  section_id: string;
  kind: StyleBeat["visual"] | "illustration";
  heading: string;
  body: string;
  source_id: string;
  quote: string;
  art_prompt?: string;
  role?: "hook" | "purpose" | "example" | "how" | "outcome" | "cta";
};
export type EpisodePlan = {
  editorial_notes?: string[];
  title: string;
  headline: string;
  script: Script;
  visuals: EpisodeVisual[];
  concept?: {
    problem: string;
    purpose: string;
    benefit: string;
    how_it_works: string;
    possible_result: string;
    limitation: string;
  } | null;
};
export type EpisodeSnapshot = {
  series: ContentSeries;
  brief: EpisodeBrief;
  angle: EpisodeAngle;
  style: SeriesStyle;
  plan: EpisodePlan;
  request_signature: string;
};
export type EpisodeDetail = { short: Short; episode: EpisodeSnapshot | null };
export const episodeThumbnailUrl = (id: string) =>
  `${API_URL}/content-series/episodes/${id}/thumbnail`;
export const visualUrl = (id: string, section: string) =>
  `${API_URL}/content-series/episodes/${id}/visuals/${section}`;

export const fontChoices = [
  { family: "Bricolage Grotesque", label: "Expressive and bold" },
  { family: "Anton", label: "Big impact headlines" },
  { family: "Space Grotesk", label: "Clean and modern" },
  { family: "Syne", label: "Playful editorial" },
  { family: "Fraunces", label: "Warm cinematic serif" },
] as const;
export const fontUrl = (family: string) =>
  `${API_URL}/content-series/fonts/${encodeURIComponent(family)}`;

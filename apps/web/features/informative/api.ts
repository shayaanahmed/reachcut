import { API_URL, responseError } from "../../lib/http";

export type ShortSettings = {
  category: "tech" | "psychology" | "history";
  style: "demo" | "explainer" | "timeline";
  language: string;
  duration: number;
  narration_mode?: "none" | "voicebox";
  profile_id: string;
  engine: string;
  model_size: string;
  delivery: string;
  pronunciations: Record<string, string>;
  audience: string;
  tone: string;
  caption_font: string;
  accent: string;
  destinations: string[];
  allow_explanation_cards: boolean;
  max_attempts: number;
  spend_limit_usd: number;
};
export const defaults: ShortSettings = {
  category: "tech",
  style: "demo",
  language: "en",
  duration: 45,
  profile_id: "",
  engine: "qwen",
  model_size: "1.7B",
  delivery: "",
  pronunciations: {},
  audience: "General audience",
  tone: "Clear and factual",
  caption_font: "Noto Sans",
  accent: "#60A5FA",
  destinations: [],
  allow_explanation_cards: false,
  max_attempts: 2,
  spend_limit_usd: 0,
};
export type Claim = {
  text: string;
  source_id: string;
  quote: string;
  status: "supported" | "interpretation" | "disputed" | "unresolved";
};
export type Section = {
  id: string;
  heading: string;
  text: string;
  visual:
    "explanation" | "screenshot" | "recording" | "diagram" | "timeline" | "map";
  claims: Claim[];
};
export type Script = { version: "1"; sections: Section[] };
export type Evidence = {
  id: string;
  title: string;
  url: string;
  retrieved_at: string;
  text: string;
};
export type Artifact = {
  audio?: boolean;
  asset?: boolean;
  duration?: number;
  generation?: string;
  submission?: string;
  attribution?: string;
  rights?: string;
  synthetic?: boolean;
  provenance?: string;
};
export type FinalVideoReview = {
  status: "passed" | "needs_refinement" | "unavailable";
  error?: string;
  basis?: string;
  history?: { pass: number }[];
  assessment?: {
    publishable: boolean;
    summary: string;
    hook_score: number;
    clarity_score: number;
    pacing_score: number;
    shareability_score: number;
    strengths: string[];
    issues: { scene: number; severity: string; message: string }[];
  };
};
export type Short = {
  final_review?: FinalVideoReview | null;
  id: string;
  topic: string;
  settings: ShortSettings;
  sources: Evidence[];
  script: Partial<Script>;
  status: string;
  phase: string;
  error: string | null;
  artifacts: Record<string, Artifact>;
  approved: boolean;
  has_output: boolean;
  findings: {
    severity: string;
    message: string;
    start: number;
    basis: string;
  }[];
  script_issues: { section: string; message: string }[];
  usage: { actual_duration_seconds?: number; actual_cost_usd?: number };
  publication_project_id: string | null;
};
export type Preset = { id: string; name: string; settings: ShortSettings };
export type Providers = {
  narration: {
    connected: boolean;
    error?: string;
    language_notice?: string;
    profiles: { id: string; name: string }[];
    engines: {
      engine: string;
      model_name: string;
      display_name: string;
      downloaded: boolean;
      languages: string[];
      supports_delivery: boolean;
    }[];
  };
  research: {
    search_configured: boolean;
    allowed_hosts: string[];
    limitation: string;
  };
};
export async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok)
    throw await responseError(response, "Could not complete this action");
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const deleteShort = (id: string) =>
  request<void>(`/shorts/${encodeURIComponent(id)}`, "DELETE");
export async function upload(
  shortId: string,
  sectionId: string,
  kind: string,
  file: File,
): Promise<Short> {
  const data = new FormData();
  data.append("file", file);
  const response = await fetch(
    `${API_URL}/shorts/${shortId}/sections/${sectionId}/upload?kind=${kind}`,
    { method: "POST", body: data },
  );
  if (!response.ok)
    throw await responseError(response, "Could not upload this asset");
  return response.json() as Promise<Short>;
}
export const shortVideoUrl = (id: string) => `${API_URL}/shorts/${id}/video`;
export const voicePreviewUrl = (id: string, generation: string) =>
  `${API_URL}/shorts/${id}/preview/${generation}`;
export const provenanceUrl = (id: string) =>
  `${API_URL}/shorts/${id}/provenance`;

export type SocialReference = {
  id: string;
  url: string;
  title: string;
  platform: string;
  channel: string;
  view_count: number | null;
  duration_seconds: number | null;
  published_at: string | null;
  description: string;
  transcript: string;
  basis: string;
};
export type CreationCapabilities = {
  platforms: { id: string; name: string; available: boolean; detail: string }[];
};

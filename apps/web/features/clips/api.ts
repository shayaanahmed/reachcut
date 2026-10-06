import { projectSchema, type Project } from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

export type ClipStyleUpdate = {
  caption_config: Project["clips"][number]["plan"]["caption_config"];
  frame_style: Project["clips"][number]["plan"]["frame_style"];
  crop_focus_x: number;
  crop_focus_y: number;
  source_slices: Project["clips"][number]["plan"]["source_slices"];
  hook_text?: string;
  hook_render: boolean;
  content_mode: Project["clips"][number]["plan"]["content_mode"];
  enhancement_level: Project["clips"][number]["plan"]["enhancement_level"];
  tracking_enabled: boolean;
  tracking_strategy: Project["clips"][number]["plan"]["tracking"]["strategy"];
  transition_style: Project["clips"][number]["plan"]["transition_style"];
  transition_duration_seconds: number;
  cta_text?: string;
  cta_render: boolean;
  cta_style?: NonNullable<Project["clips"][number]["plan"]["cta"]>["style"];
  effects: Project["clips"][number]["plan"]["effects"];
  audio_track_index: number;
};

export async function updateClipStyle(
  clipId: string,
  data: ClipStyleUpdate,
): Promise<Project> {
  const response = await fetch(`${API_URL}/clips/${clipId}/style`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok)
    throw await responseError(response, "Could not update clip style");
  return projectSchema.parse(await response.json());
}

export async function translateClip(
  clipId: string,
  targetLanguage: string,
  mode: "translated" | "bilingual",
): Promise<Project> {
  const response = await fetch(`${API_URL}/clips/${clipId}/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_language: targetLanguage, mode }),
  });
  if (!response.ok)
    throw await responseError(response, "Could not translate captions");
  return projectSchema.parse(await response.json());
}

export async function analyzeClipTracking(clipId: string): Promise<Project> {
  const response = await fetch(`${API_URL}/clips/${clipId}/tracking`, {
    method: "POST",
  });
  if (!response.ok)
    throw await responseError(response, "Could not analyze visual tracking");
  return projectSchema.parse(await response.json());
}

export async function uploadClipSecondaryMedia(
  clipId: string,
  data: FormData,
): Promise<Project> {
  const response = await fetch(`${API_URL}/clips/${clipId}/secondary-media`, {
    method: "POST",
    body: data,
  });
  if (!response.ok)
    throw await responseError(response, "Could not attach secondary media");
  return projectSchema.parse(await response.json());
}

export async function deleteClipSecondaryMedia(
  clipId: string,
  assetId: string,
): Promise<Project> {
  const response = await fetch(
    `${API_URL}/clips/${clipId}/secondary-media/${assetId}`,
    { method: "DELETE" },
  );
  if (!response.ok)
    throw await responseError(response, "Could not remove secondary media");
  return projectSchema.parse(await response.json());
}

export async function setApproval(
  clipId: string,
  approved: boolean,
): Promise<Project> {
  const response = await fetch(`${API_URL}/clips/${clipId}/approval`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
  if (!response.ok)
    throw new Error(`Could not update approval (${response.status})`);
  return projectSchema.parse(await response.json());
}

export const previewUrl = (clipId: string) =>
  `${API_URL}/clips/${clipId}/preview`;

export const finalUrl = (clipId: string) => `${API_URL}/clips/${clipId}/final`;

export async function renderClip(clipId: string): Promise<void> {
  const response = await fetch(`${API_URL}/clips/${clipId}/render`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(`Final render failed (${response.status})`);
}

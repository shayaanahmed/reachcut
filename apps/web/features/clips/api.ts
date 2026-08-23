import { projectSchema, type Project } from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

export type ClipStyleUpdate = {
  caption_config: Project["clips"][number]["plan"]["caption_config"];
  frame_style: Project["clips"][number]["plan"]["frame_style"];
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

import { z } from "zod";

import {
  videoTemplateIdSchema,
  type VideoTemplateId,
} from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

const blueprintSchema = z.object({
  name: z.string(),
  base_template: videoTemplateIdSchema,
  format: z.string(),
  tags: z.array(z.string()),
  visual_style: z.string(),
  camera: z.string(),
  pacing: z.string(),
  story_structure: z.string(),
  caption_style: z.string(),
  suitable_for: z.string(),
});
const referenceSchema = z.object({
  id: z.string(),
  name: z.string(),
  source_url: z.string().nullable(),
  source_category: z.string().nullable(),
  status: z.enum(["pending", "ready", "failed"]),
  blueprint: blueprintSchema.nullable(),
  duration_seconds: z.number(),
  error: z.string().nullable(),
  analysis_model: z.string().nullable(),
  video_url: z.string().nullable(),
  poster_url: z.string().nullable(),
});
export type ReferenceTemplate = z.infer<typeof referenceSchema>;
export type ReferenceSelection = "none" | "auto" | string;
export type ResolvedReference = {
  template: VideoTemplateId;
  reference_template_id: string;
  reason: string;
};

const path = "/video-generation/template-library";

export async function listReferenceTemplates(): Promise<ReferenceTemplate[]> {
  return referenceSchema.array().parse(await request(path));
}
export async function classifyReferenceTemplate(
  id: string,
): Promise<ReferenceTemplate> {
  return referenceSchema.parse(
    await request(`${path}/${id}/classify`, { method: "POST" }),
  );
}
export async function importReferenceTemplate(
  url: string,
): Promise<ReferenceTemplate> {
  return referenceSchema.parse(
    await request(`${path}/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }),
  );
}
export async function uploadReferenceTemplate(
  file: File,
): Promise<ReferenceTemplate> {
  const body = new FormData();
  body.append("video", file);
  body.append("name", file.name.slice(0, 100));
  return referenceSchema.parse(
    await request(`${path}/upload`, { method: "POST", body }),
  );
}
export async function resolveReferenceTemplate(
  selection: ReferenceSelection,
  prompt: string,
): Promise<ResolvedReference | null> {
  if (selection === "none") return null;
  const references = await listReferenceTemplates();
  let id = selection;
  let reason = "Selected reference template";
  if (selection === "auto") {
    const match = z
      .object({ template_id: z.string(), reason: z.string() })
      .parse(
        await request(`${path}/match`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt }),
        }),
      );
    id = match.template_id;
    reason = match.reason;
  }
  const selected = references.find(
    (item) => item.id === id && item.status === "ready",
  );
  if (!selected?.blueprint)
    throw new Error("Classify this reference before using it");
  return {
    template: selected.blueprint.base_template,
    reference_template_id: selected.id,
    reason,
  };
}
export function referencePosterUrl(
  item: ReferenceTemplate,
): string | undefined {
  if (!item.poster_url) return undefined;
  if (item.poster_url.startsWith("https://")) return item.poster_url;
  return API_URL.startsWith("http")
    ? `${API_URL}${item.poster_url.replace(/^\/api/, "")}`
    : item.poster_url;
}
export function referenceVideoUrl(item: ReferenceTemplate): string | undefined {
  if (!item.video_url) return item.source_url ?? undefined;
  return API_URL.startsWith("http")
    ? `${API_URL}${item.video_url.replace(/^\/api/, "")}`
    : item.video_url;
}
async function request(url: string, options?: RequestInit): Promise<unknown> {
  const response = await fetch(
    `${API_URL}${url}`,
    options ?? { cache: "no-store" },
  );
  if (!response.ok)
    throw await responseError(response, "Reference template request failed");
  return response.json();
}

import {
  generatedVideoSchema,
  localVideoReadinessSchema,
  storyPlanSchema,
  videoGenerationTemplateSchema,
  type GeneratedVideo,
  type LocalVideoReadiness,
  type StoryPlan,
  type VideoGenerationTemplate,
  type VideoTemplateId,
} from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

export type StorySettings = {
  visual_style_override?: boolean;
  template: VideoTemplateId;
  aspect_ratio: "9:16" | "16:9" | "1:1";
  reference_template_id?: string;
  shot_mode?: "auto" | "continuous" | "story";
  narration_enabled?: boolean;
};

export async function listVideoTemplates(): Promise<VideoGenerationTemplate[]> {
  return getParsed(
    "/video-generation/templates",
    videoGenerationTemplateSchema.array(),
    "Could not load story styles",
  );
}

export async function getVideoReadiness(): Promise<LocalVideoReadiness> {
  return getParsed(
    "/video-generation/readiness",
    localVideoReadinessSchema,
    "Could not inspect the local video engine",
  );
}

export async function startVideoEngine(): Promise<LocalVideoReadiness> {
  const response = await fetch(`${API_URL}/video-generation/engine/start`, {
    method: "POST",
  });
  if (!response.ok)
    throw await responseError(
      response,
      "Could not start the local video engine",
    );
  return localVideoReadinessSchema.parse(await response.json());
}

export async function authorizeHuggingFace(): Promise<string> {
  const response = await fetch(
    `${API_URL}/video-generation/engine/huggingface-login`,
    { method: "POST" },
  );
  if (!response.ok)
    throw await responseError(
      response,
      "Could not start Hugging Face authorization",
    );
  const payload = (await response.json()) as { authorization_url: string };
  return payload.authorization_url;
}

export async function downloadVideoModels(): Promise<string> {
  const response = await fetch(
    `${API_URL}/video-generation/engine/download-models`,
    {
      method: "POST",
    },
  );
  if (!response.ok)
    throw await responseError(
      response,
      "Could not start the LTX model download",
    );
  const payload = (await response.json()) as { session_id: string };
  return payload.session_id;
}

export async function createStoryIdea(
  idea: string,
  template: VideoTemplateId,
  referenceTemplateId?: string,
  visualStyleOverride = false,
  signal?: AbortSignal,
): Promise<{ story: string; hook: string }> {
  const response = await post(
    "/video-generation/idea",
    {
      idea,
      template,
      ...(visualStyleOverride ? { visual_style_override: true } : {}),
      ...(referenceTemplateId
        ? { reference_template_id: referenceTemplateId }
        : {}),
    },
    signal,
  );
  return (await response.json()) as { story: string; hook: string };
}

export async function planStory(
  story: string,
  settings: StorySettings,
  targetDurationSeconds: 10 | 15 | 20 | 30 | 45 | 60,
  signal?: AbortSignal,
): Promise<StoryPlan> {
  const response = await post(
    "/video-generation/plan",
    {
      story,
      ...settings,
      target_duration_seconds: targetDurationSeconds,
    },
    signal,
  );
  return storyPlanSchema.parse(await response.json());
}

export async function listGeneratedVideos(): Promise<GeneratedVideo[]> {
  return getParsed(
    "/video-generation",
    generatedVideoSchema.array(),
    "Could not load story videos",
  );
}

export async function generateVideo(
  request: {
    story: string;
    draft_id?: string;
    plan: StoryPlan;
    quality: "draft" | "1080p";
    reference_id?: string;
  } & StorySettings,
): Promise<GeneratedVideo> {
  const response = await post("/video-generation", request);
  return generatedVideoSchema.parse(await response.json());
}

export async function uploadStoryReference(file: File): Promise<string> {
  const body = new FormData();
  body.append("image", file);
  const response = await fetch(`${API_URL}/video-generation/references`, {
    method: "POST",
    body,
  });
  if (!response.ok)
    throw await responseError(
      response,
      "Could not upload the character reference",
    );
  const payload = (await response.json()) as { id: string };
  return payload.id;
}

export async function getGeneratedVideo(id: string): Promise<GeneratedVideo> {
  return getParsed(
    `/video-generation/${id}`,
    generatedVideoSchema,
    "Could not update generation progress",
  );
}

export async function resumeGeneratedVideo(
  id: string,
): Promise<GeneratedVideo> {
  const response = await fetch(`${API_URL}/video-generation/${id}/resume`, {
    method: "POST",
  });
  if (!response.ok)
    throw await responseError(response, "Could not resume generation");
  return generatedVideoSchema.parse(await response.json());
}

export async function deleteGeneratedVideo(id: string): Promise<void> {
  const response = await fetch(`${API_URL}/video-generation/${id}`, {
    method: "DELETE",
  });
  if (!response.ok)
    throw await responseError(response, "Could not delete story video");
}

export function generatedVideoUrl(video: GeneratedVideo): string | null {
  if (!video.video_url) return null;
  if (!API_URL.startsWith("http")) return video.video_url;
  return `${API_URL}${video.video_url.replace(/^\/api/, "")}`;
}

async function post(
  path: string,
  body: object,
  signal?: AbortSignal,
): Promise<Response> {
  signal?.throwIfAborted();
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok)
    throw await responseError(response, "Local AI request failed");
  return response;
}

async function getParsed<T>(
  path: string,
  schema: { parse: (value: unknown) => T },
  message: string,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) throw await responseError(response, message);
  return schema.parse(await response.json());
}

export type StoryDraftSettings = Omit<StorySettings, "template"> & {
  story: string;
  template: VideoTemplateId | null;
  quality: "draft" | "1080p";
  target_duration_seconds: 10 | 15 | 20 | 30 | 45 | 60;
  reference_id?: string;
};
export type StoryDraft = {
  id: string;
  story: string;
  settings: StoryDraftSettings;
  created_at: string;
};
export async function listStoryDrafts(): Promise<StoryDraft[]> {
  const response = await fetch(`${API_URL}/video-generation/drafts`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw await responseError(response, "Could not load the story queue");
  return response.json();
}
export async function saveStoryDraft(
  settings: StoryDraftSettings,
  id?: string,
): Promise<StoryDraft> {
  const response = await fetch(
    `${API_URL}/video-generation/drafts${id ? `/${id}` : ""}`,
    {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    },
  );
  if (!response.ok)
    throw await responseError(response, "Could not save queued story");
  return response.json();
}
export async function deleteStoryDraft(id: string): Promise<void> {
  const response = await fetch(`${API_URL}/video-generation/drafts/${id}`, {
    method: "DELETE",
  });
  if (!response.ok)
    throw await responseError(response, "Could not remove queued story");
}
export async function matchStoryFormat(
  story: string,
  signal?: AbortSignal,
): Promise<{
  template: VideoTemplateId;
  reference_template_id: string | null;
  reason: string;
}> {
  const response = await post(
    "/video-generation/match-format",
    { story },
    signal,
  );
  return response.json();
}
export async function renameGeneratedVideo(
  id: string,
  title: string,
): Promise<GeneratedVideo> {
  const response = await fetch(`${API_URL}/video-generation/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok)
    throw await responseError(response, "Could not rename short");
  return generatedVideoSchema.parse(await response.json());
}
export async function prepareStoryPublishing(
  id: string,
): Promise<{ project_id: string; clip_id: string }> {
  const response = await post(`/video-generation/${id}/publishing`, {});
  return response.json();
}

export async function stopGeneratedVideo(id: string): Promise<GeneratedVideo> {
  const response = await post(`/video-generation/${id}/cancel`, {});
  return generatedVideoSchema.parse(await response.json());
}

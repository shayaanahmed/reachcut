import { z } from "zod";
import { socialPlatformSchema } from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

export const audienceSchema = z.object({
  audience: z.string(),
  niche: z.string(),
  language: z.string(),
  country: z.string(),
});
export const platformCopySchema = z.object({
  platform: socialPlatformSchema,
  title: z.string(),
  caption: z.string(),
  cover_text: z.string(),
  hashtags: z.array(z.string()),
});
export type PlatformCopy = z.infer<typeof platformCopySchema>;
export const growthBriefSchema = z.object({
  automatic: z.boolean().default(false),
  account_id: z.string().nullable(),
  profile: audienceSchema,
  target_query: z.string(),
  evidence: z.array(
    z.object({
      query: z.string(),
      source_url: z.string(),
      observed_at: z.string(),
      notes: z.string(),
    }),
  ),
  creative: z
    .object({
      openings: z.array(
        z.object({ opening_line: z.string(), first_frame: z.string() }),
      ),
      packages: z.array(platformCopySchema),
      experiment: z.string(),
    })
    .nullable(),
});
export type GrowthBrief = z.infer<typeof growthBriefSchema>;
export const diagnosisSchema = z.object({
  publication_id: z.string(),
  clip_id: z.string(),
  project_id: z.string(),
  title: z.string(),
  platform: z.string(),
  account_id: z.string().nullable(),
  views: z.number(),
  baseline_views: z.number().nullable(),
  baseline_posts: z.number(),
  relative_views: z.number().nullable(),
  sends_per_reach: z.number().nullable(),
  search_share: z.number().nullable(),
  average_watch_seconds: z.number().nullable(),
  confidence: z.string(),
  findings: z.array(z.string()),
  actions: z.array(z.string()),
});
export type GrowthDiagnosis = z.infer<typeof diagnosisSchema>;
export const growthStateSchema = z.object({
  automatic_enabled: z.boolean().default(true),
  preparation: z
    .object({
      status: z.string(),
      error: z.string().nullable(),
      reasoning: z.string().nullable(),
    })
    .nullable()
    .default(null),
  brief: growthBriefSchema,
  profiles: z.record(z.string(), audienceSchema),
  diagnoses: z.array(diagnosisSchema),
});

async function request(path: string, method = "GET", body?: unknown) {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (response.status === 422) {
    const errors = z
      .object({
        detail: z.array(
          z.object({
            loc: z.array(z.union([z.string(), z.number()])),
            msg: z.string(),
          }),
        ),
      })
      .safeParse(await response.json());
    throw new Error(
      errors.success
        ? errors.data.detail
            .map(
              (e) => `${e.loc.filter((v) => v !== "body").join(".")}: ${e.msg}`,
            )
            .join("; ")
        : "Check the growth brief fields and try again.",
    );
  }
  if (!response.ok)
    throw await responseError(response, "Could not load or save growth brief");
  return response.json();
}
export async function loadGrowth(clipId: string) {
  return growthStateSchema.parse(await request(`/clips/${clipId}/growth`));
}
export async function saveGrowth(clipId: string, brief: GrowthBrief) {
  return growthBriefSchema.parse(
    await request(`/clips/${clipId}/growth`, "PUT", brief),
  );
}
export async function generateGrowth(clipId: string, brief: GrowthBrief) {
  return growthBriefSchema.parse(
    await request(`/clips/${clipId}/growth/generate`, "POST", brief),
  );
}
export async function loadGrowthInsights() {
  return z.array(diagnosisSchema).parse(await request("/growth/insights"));
}

export async function prepareGrowth(clipId: string) {
  return growthStateSchema.parse(
    await request(`/clips/${clipId}/growth/prepare`, "POST"),
  );
}

export async function loadPublishingCopy(clipId: string) {
  const response = await fetch(`${API_URL}/clips/${clipId}/publishing-copy`, {
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok)
    throw await responseError(
      response,
      "Could not load the latest publishing draft",
    );
  return z
    .object({
      packages: z.array(platformCopySchema),
      hashtag_notice: z.string().nullable(),
    })
    .parse(await response.json());
}

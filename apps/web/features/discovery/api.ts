import { z } from "zod";

import { API_URL, responseError } from "../../lib/http";

const country = z.object({ code: z.string(), name: z.string() });

export const discoveryResultSchema = z.object({
  country,
  query: z.string().nullable().default(null),
  category: z.string().default("trending"),
  fetched_at: z.string(),
  topics: z.array(
    z.object({
      title: z.string(),
      approximate_traffic: z.string().nullable(),
      news_title: z.string().nullable(),
      news_url: z.string().nullable(),
    }),
  ),
  sources: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      url: z.string(),
      channel: z.string().nullable(),
      thumbnail_url: z.string().nullable(),
      duration_seconds: z.number().nullable(),
      view_count: z.number().nullable(),
      published_at: z.string().nullable(),
      opportunity_type: z.enum(["trending_interview", "upcoming_interview"]),
      topic: z.string(),
      is_upcoming: z.boolean(),
      source_score: z.number(),
    }),
  ),
  note: z.string(),
});

export type DiscoveryResult = z.infer<typeof discoveryResultSchema>;
export type SourceCandidate = DiscoveryResult["sources"][number];

export type DiscoveryRequest = {
  query?: string;
  category?: string;
};

export async function discoverOpportunities(
  request: DiscoveryRequest = {},
): Promise<DiscoveryResult> {
  const parameters = new URLSearchParams({
    country: "US",
    limit: "12",
    category: request.category || "trending",
  });
  if (request.query?.trim()) parameters.set("query", request.query.trim());
  const response = await fetch(`${API_URL}/discovery?${parameters}`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw await responseError(response, "Could not fetch trend opportunities");
  return discoveryResultSchema.parse(await response.json());
}

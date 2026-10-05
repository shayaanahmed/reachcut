import { z } from "zod";

export const socialPlatformSchema = z.enum([
  "youtube",
  "tiktok",
  "instagram",
  "facebook",
  "x",
]);

const timeRange = z.object({
  start_seconds: z.number(),
  end_seconds: z.number(),
});
const editingPlan = z.object({
  schema_version: z.literal("1.0"),
  source: timeRange,
  scores: z.object({
    overall: z.number(),
    hook: z.number(),
    clarity: z.number(),
    payoff: z.number(),
    visual_interest: z.number(),
  }),
  rationale: z.string(),
  suggested_title: z.string().nullable().default(null),
  hashtags: z.array(z.string()).default([]),
  hook: timeRange.extend({ text: z.string() }).nullable(),
  caption_style: z.enum(["clean", "kinetic_highlight", "karaoke"]),
  caption_config: z
    .object({
      enabled: z.boolean().default(true),
      position: z.enum(["top", "middle", "bottom"]),
      font_family: z.string(),
      font_size: z.number(),
      text_color: z.string(),
      highlight_color: z.string(),
      outline_color: z.string(),
      animation: z.enum(["none", "pop", "karaoke"]),
      highlighted_words: z.array(z.string()),
      max_words_per_line: z.number(),
    })
    .default({
      enabled: true,
      position: "bottom",
      font_family: "Noto Sans",
      font_size: 58,
      text_color: "#FFFFFF",
      highlight_color: "#D8FF42",
      outline_color: "#111111",
      animation: "pop",
      highlighted_words: [],
      max_words_per_line: 5,
    }),
  frame_style: z
    .enum(["blurred_background", "center_crop"])
    .default("blurred_background"),
  emphasis: z.array(z.unknown()),
  effects: z.array(z.unknown()),
  cta: timeRange.extend({ text: z.string() }).nullable(),
});

const metricSnapshot = z.object({
  id: z.number(),
  recorded_at: z.string(),
  views: z.number(),
  likes: z.number(),
  comments: z.number(),
  shares: z.number(),
  watch_time_seconds: z.number().nullable(),
  followers_gained: z.number(),
  affiliate_clicks: z.number(),
  conversions: z.number(),
  revenue: z.number(),
  currency: z.string(),
});

const publication = z.object({
  id: z.string(),
  platform: socialPlatformSchema,
  status: z.enum(["ready", "processing", "published", "failed"]),
  post_url: z.string().nullable(),
  title: z.string(),
  description: z.string(),
  published_at: z.string().nullable(),
  created_at: z.string(),
  social_account_id: z.string().nullable().default(null),
  account_label: z.string().nullable().default(null),
  account_username: z.string().nullable().default(null),
  provider_publication_id: z.string().nullable().default(null),
  metric_snapshots: z.array(metricSnapshot),
});

export const socialAccountSchema = z.object({
  id: z.string(),
  platform: socialPlatformSchema,
  label: z.string(),
  username: z.string(),
  profile_url: z.string().nullable(),
  default_hashtags: z.array(z.string()),
  default_cta: z.string(),
  default_campaign_url: z.string().nullable(),
  currency: z.string(),
  connection_status: z.string(),
  is_default: z.boolean(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const projectSchema = z.object({
  id: z.string(),
  title: z.string(),
  original_filename: z.string(),
  status: z.string(),
  duration_seconds: z.number().nullable(),
  authorization_confirmed_at: z.string(),
  created_at: z.string(),
  stages: z.array(
    z.object({
      name: z.string(),
      status: z.string(),
      progress: z.number(),
      attempts: z.number(),
      error: z.record(z.string(), z.unknown()).nullable(),
    }),
  ),
  clips: z.array(
    z.object({
      id: z.string(),
      approval_status: z.string(),
      plan: editingPlan,
      preview_path: z.string().nullable(),
      final_path: z.string().nullable(),
      publish_recommendation: z
        .object({
          score: z.number(),
          confidence: z.enum(["high", "medium", "low"]),
          reasons: z.array(z.string()),
        })
        .default({ score: 0, confidence: "low", reasons: [] }),
      publications: z.array(publication).default([]),
    }),
  ),
});

export type Project = z.infer<typeof projectSchema>;
export type SocialAccount = z.infer<typeof socialAccountSchema>;
export type SocialPlatform = z.infer<typeof socialPlatformSchema>;

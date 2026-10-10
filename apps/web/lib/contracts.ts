import { z } from "zod";

export const socialPlatformSchema = z.enum([
  "youtube",
  "tiktok",
  "instagram",
  "facebook",
  "x",
]);

export const clipTypeSchema = z.enum([
  "highlight",
  "funny",
  "advice",
  "insight",
  "story",
  "debate",
  "educational",
  "emotional",
  "promotional",
]);

const timeRange = z.object({
  start_seconds: z.number(),
  end_seconds: z.number(),
});
const contentMode = z.enum([
  "auto",
  "talking_head",
  "podcast",
  "gameplay",
  "sports",
  "tutorial",
  "reaction",
  "product",
  "news",
  "broll",
]);
const effect = z.object({
  time_seconds: z.number(),
  type: z.enum([
    "punch_zoom",
    "slow_zoom",
    "sound_effect",
    "progress_bar",
    "speaker_label",
    "question_card",
    "quote_card",
  ]),
  parameters: z.record(z.string(), z.unknown()).default({}),
});
const editingPlan = z.object({
  schema_version: z.literal("1.0"),
  source: timeRange,
  source_slices: z.array(timeRange).default([]),
  optimization_goal: z.enum(["views", "revenue"]).default("views"),
  content_mode: contentMode.default("auto"),
  clip_type: clipTypeSchema.default("highlight"),
  enhancement_level: z
    .enum(["clean", "dynamic", "aggressive"])
    .default("clean"),
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
  hook: timeRange
    .extend({ text: z.string(), render: z.boolean().default(false) })
    .nullable(),
  caption_style: z.enum(["clean", "kinetic_highlight", "karaoke"]),
  caption_config: z
    .object({
      preset: z
        .enum([
          "custom",
          "clean",
          "bold_viral",
          "karaoke",
          "podcast",
          "gaming",
          "sports",
          "minimal",
          "news",
        ])
        .default("custom"),
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
      text_override: z.string().nullable().default(null),
      source_language: z.string().nullable().default(null),
      target_language: z.string().nullable().default(null),
      translation_mode: z
        .enum(["original", "translated", "bilingual"])
        .default("original"),
      translated_text: z.string().nullable().default(null),
    })
    .default({
      preset: "custom",
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
      text_override: null,
      source_language: null,
      target_language: null,
      translation_mode: "original",
      translated_text: null,
    }),
  frame_style: z
    .enum(["blurred_background", "center_crop"])
    .default("blurred_background"),
  crop_focus_x: z.number().default(0.5),
  crop_focus_y: z.number().default(0.5),
  tracking: z
    .object({
      enabled: z.boolean().default(false),
      strategy: z
        .enum(["static", "face", "active_speaker", "action", "object"])
        .default("static"),
      keyframes: z
        .array(
          z.object({
            time_seconds: z.number(),
            center_x: z.number(),
            center_y: z.number(),
            confidence: z.number().default(1),
          }),
        )
        .default([]),
    })
    .default({ enabled: false, strategy: "static", keyframes: [] }),
  transition_style: z.enum(["cut", "fade"]).default("cut"),
  transition_duration_seconds: z.number().default(0.2),
  secondary_media: z
    .array(
      z.object({
        asset_id: z.string(),
        filename: z.string(),
        kind: z.enum([
          "gameplay",
          "broll",
          "reaction",
          "sound_effect",
          "music",
        ]),
        start_seconds: z.number().nullable().default(null),
        end_seconds: z.number().nullable().default(null),
        muted: z.boolean().default(true),
        loop: z.boolean().default(true),
        volume_db: z.number().default(-18),
        placement: z
          .enum(["bottom", "pip", "fullscreen", "audio"])
          .default("bottom"),
      }),
    )
    .default([]),
  audio_track_index: z.number().default(0),
  emphasis: z.array(z.unknown()),
  effects: z.array(effect),
  cta: timeRange
    .extend({
      text: z.string(),
      render: z.boolean().default(false),
      style: z
        .enum([
          "follow",
          "comment",
          "part_two",
          "profile",
          "product",
          "campaign",
        ])
        .default("follow"),
    })
    .nullable(),
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

export const accountConnectionReadinessSchema = z.object({
  account_id: z.string(),
  platform: socialPlatformSchema,
  provider_configured: z.boolean(),
  credentials_available: z.boolean(),
  publishing_ready: z.boolean(),
  issues: z.array(z.string()),
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

export const clipTypeSuggestionSchema = z.object({
  clip_type: clipTypeSchema,
  score: z.number(),
  reason: z.string(),
});

export const runtimeSettingsSchema = z.object({
  ollama_base_url: z.string(),
  editorial_model: z.string(),
});

export const automationPipelineSchema = z.object({
  id: z.string(),
  name: z.string(),
  project_id: z.string(),
  social_account_ids: z.array(z.string()),
  clip_selection: z.enum(["all", "best"]),
  clip_types: z.array(clipTypeSchema),
  schedule: z.enum(["once", "daily", "weekly"]),
  next_run_at: z.string(),
  status: z.string(),
  auto_approve: z.boolean(),
  title_template: z.string(),
  description_template: z.string(),
  last_run_at: z.string().nullable(),
  last_error: z.string().nullable(),
  created_at: z.string(),
});

export type Project = z.infer<typeof projectSchema>;
export type SocialAccount = z.infer<typeof socialAccountSchema>;
export type SocialPlatform = z.infer<typeof socialPlatformSchema>;
export type AccountConnectionReadiness = z.infer<
  typeof accountConnectionReadinessSchema
>;
export type ClipType = z.infer<typeof clipTypeSchema>;
export type ClipTypeSuggestion = z.infer<typeof clipTypeSuggestionSchema>;
export type RuntimeSettings = z.infer<typeof runtimeSettingsSchema>;
export type AutomationPipeline = z.infer<typeof automationPipelineSchema>;

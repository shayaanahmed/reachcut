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
  video_template: z
    .enum(["custom", "clean_focus", "bold_viral", "podcast", "story"])
    .default("custom"),
  scores: z.object({
    overall: z.number(),
    hook: z.number(),
    clarity: z.number(),
    payoff: z.number(),
    visual_interest: z.number(),
  }),
  rationale: z.string(),
  suggested_title: z.string().nullable().default(null),
  thumbnail: z
    .object({
      template: z
        .enum(["speaker", "question", "cinematic", "minimal"])
        .default("speaker"),
      headline: z.string().nullable().default(null),
      frame_time_seconds: z.number().nullable().default(null),
      generated: z.boolean().default(false),
    })
    .default({
      template: "speaker",
      headline: null,
      frame_time_seconds: null,
      generated: false,
    }),
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
  error: z.string().nullable().optional(),
  id: z.string(),
  platform: socialPlatformSchema,
  status: z.enum(["ready", "queued", "processing", "published", "failed"]),
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
  external_account_id: z.string().nullable().optional(),
  parent_page_name: z.string().nullable().optional(),
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

export const socialAccountGroupSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  account_ids: z.array(z.string()),
});
export type SocialAccountGroup = z.infer<typeof socialAccountGroupSchema>;

export const oauthAccountSelectionSchema = z.object({
  platform: socialPlatformSchema,
  candidates: z.array(
    z.object({
      external_account_id: z.string(),
      display_name: z.string(),
      username: z.string(),
      parent_page_name: z.string(),
      already_connected: z.boolean(),
    }),
  ),
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
  job: z
    .object({
      status: z.string(),
      phase: z.string(),
      source_url: z.string().nullable(),
      error: z.string().nullable(),
      enqueued_at: z.string(),
    })
    .nullable()
    .optional(),
  id: z.string(),
  title: z.string(),
  original_filename: z.string(),
  status: z.string(),
  duration_seconds: z.number().nullable(),
  storage_bytes: z.number().nonnegative().default(0),
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
      thumbnail_ready: z.boolean().default(false),
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
  thumbnail_model: z.string(),
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

export const videoTemplateIdSchema = z.enum([
  "cinematic_story",
  "animated_adventure",
  "anime_story",
  "stylized_3d",
  "dark_mystery",
  "documentary_realism",
]);

export const videoGenerationTemplateSchema = z.object({
  id: videoTemplateIdSchema,
  name: z.string(),
  description: z.string(),
  category: z.string(),
  prompt_hint: z.string(),
  style_prompt: z.string(),
  palette: z.tuple([z.string(), z.string(), z.string()]),
  badge: z.string(),
});

export const storyCharacterSchema = z.object({
  id: z.string(),
  name: z.string(),
  role: z.string(),
  appearance_anchor: z.string(),
  wardrobe_anchor: z.string(),
  voice_anchor: z.string(),
});

export const storySceneSchema = z.object({
  crop: z
    .object({
      x: z.number(),
      y: z.number(),
      width: z.number(),
      height: z.number(),
    })
    .nullable()
    .optional(),
  trim_start_seconds: z.number().optional(),
  trim_end_seconds: z.number().nullable().optional(),
  playback_speed: z.number().optional(),
  opening_frame: z.string().optional(),
  ending_frame: z.string().optional(),
  index: z.number(),
  title: z.string(),
  story_beat: z.string(),
  narration: z.string(),
  visual_prompt: z.string(),
  character_ids: z.array(z.string()),
  camera_motion: z.enum([
    "none",
    "static",
    "focus_shift",
    "dolly_in",
    "dolly_out",
    "dolly_left",
    "dolly_right",
    "jib_up",
    "jib_down",
  ]),
  duration_seconds: z.union([z.literal(5), z.literal(10)]),
  seed: z.number(),
});

export const storyPlanSchema = z.object({
  continuity_notes: z.string().optional(),
  hook_caption: z.string().optional(),
  end_caption: z.string().optional(),
  title: z.string(),
  logline: z.string(),
  visual_style: z.string(),
  negative_prompt: z.string(),
  characters: z.array(storyCharacterSchema),
  scenes: z.array(storySceneSchema),
});

export const storyVideoSceneSchema = z.object({
  id: z.string(),
  scene_index: z.number(),
  title: z.string(),
  prompt: z.string(),
  narration: z.string(),
  duration_seconds: z.number(),
  seed: z.number(),
  status: z.string(),
  progress: z.number(),
  error: z.string().nullable(),
});

export const generatedVideoSchema = z.object({
  id: z.string(),
  story: z.string(),
  template: videoTemplateIdSchema,
  aspect_ratio: z.enum(["9:16", "16:9", "1:1"]),
  quality: z.enum(["draft", "1080p"]),
  target_duration_seconds: z.number(),
  status: z.string(),
  phase: z.string(),
  progress: z.number(),
  plan: storyPlanSchema,
  provider: z.string(),
  error: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  scenes: z.array(storyVideoSceneSchema),
  video_url: z.string().nullable(),
});

export const localVideoReadinessSchema = z.object({
  ready: z.boolean(),
  ollama_connected: z.boolean(),
  ollama_model_ready: z.boolean(),
  engine_installed: z.boolean(),
  engine_running: z.boolean(),
  models_ready: z.boolean(),
  hf_authenticated: z.boolean(),
  download_status: z.string(),
  download_progress: z.number().min(0).max(1),
  engine_name: z.string(),
  detail: z.string(),
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
export type GeneratedVideo = z.infer<typeof generatedVideoSchema>;
export type StoryPlan = z.infer<typeof storyPlanSchema>;
export type StoryScene = z.infer<typeof storySceneSchema>;
export type LocalVideoReadiness = z.infer<typeof localVideoReadinessSchema>;
export type VideoGenerationTemplate = z.infer<
  typeof videoGenerationTemplateSchema
>;
export type VideoTemplateId = z.infer<typeof videoTemplateIdSchema>;

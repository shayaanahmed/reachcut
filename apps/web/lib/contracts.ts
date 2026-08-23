import { z } from "zod";

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
  hook: timeRange.extend({ text: z.string() }).nullable(),
  caption_style: z.enum(["clean", "kinetic_highlight", "karaoke"]),
  caption_config: z
    .object({
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
    }),
  ),
});

export type Project = z.infer<typeof projectSchema>;

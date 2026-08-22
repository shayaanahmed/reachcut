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

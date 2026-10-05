import { describe, expect, it } from "vitest";

import { projectSchema } from "../../lib/contracts";
import { summarizeWorkspace } from "./dashboard";

describe("dashboard summary", () => {
  it("uses only the latest metrics snapshot from each publication", () => {
    const project = projectSchema.parse({
      id: "project-1",
      title: "Project",
      original_filename: "source.mp4",
      status: "review",
      duration_seconds: 120,
      authorization_confirmed_at: "2026-10-02T10:00:00Z",
      created_at: "2026-10-02T10:00:00Z",
      stages: [],
      clips: [
        {
          id: "clip-1",
          approval_status: "approved",
          preview_path: null,
          final_path: "/clips/clip-1/final.mp4",
          plan: {
            schema_version: "1.0",
            source: { start_seconds: 0, end_seconds: 30 },
            scores: {
              overall: 90,
              hook: 90,
              clarity: 90,
              payoff: 90,
              visual_interest: 90,
            },
            rationale: "A useful clip.",
            suggested_title: "Useful clip",
            hashtags: [],
            hook: null,
            caption_style: "clean",
            emphasis: [],
            effects: [],
            cta: null,
          },
          publications: [
            {
              id: "publication-1",
              platform: "youtube",
              status: "published",
              post_url: "https://youtube.com/watch?v=example",
              title: "Useful clip",
              description: "",
              published_at: "2026-10-02T10:00:00Z",
              created_at: "2026-10-02T10:00:00Z",
              metric_snapshots: [
                {
                  id: 1,
                  recorded_at: "2026-10-02T11:00:00Z",
                  views: 100,
                  likes: 10,
                  comments: 0,
                  shares: 0,
                  watch_time_seconds: null,
                  followers_gained: 0,
                  affiliate_clicks: 0,
                  conversions: 0,
                  revenue: 0,
                  currency: "EUR",
                },
                {
                  id: 2,
                  recorded_at: "2026-10-03T11:00:00Z",
                  views: 1000,
                  likes: 80,
                  comments: 10,
                  shares: 10,
                  watch_time_seconds: null,
                  followers_gained: 0,
                  affiliate_clicks: 0,
                  conversions: 0,
                  revenue: 0,
                  currency: "EUR",
                },
              ],
            },
          ],
        },
      ],
    });

    expect(summarizeWorkspace([project])).toEqual({
      projects: 1,
      views: 1000,
      published: 1,
      exported: 1,
      engagementRate: 10,
      attention: 1,
    });
  });
});

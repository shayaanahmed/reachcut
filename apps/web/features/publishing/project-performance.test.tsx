import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { projectSchema } from "../../lib/contracts";
import { ProjectPerformance } from "./project-performance";

describe("project performance", () => {
  it("summarizes the latest metric snapshot for every publication", () => {
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
            hashtags: ["#Useful"],
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
              post_url: "https://youtube.com/shorts/example",
              title: "Useful clip",
              description: "#Useful",
              published_at: "2026-10-02T10:00:00Z",
              created_at: "2026-10-02T10:00:00Z",
              metric_snapshots: [
                {
                  id: 1,
                  recorded_at: "2026-10-02T11:00:00Z",
                  views: 100,
                  likes: 10,
                  comments: 2,
                  shares: 3,
                  watch_time_seconds: 1000,
                  followers_gained: 2,
                  affiliate_clicks: 1,
                  conversions: 1,
                  revenue: 5,
                  currency: "EUR",
                },
                {
                  id: 2,
                  recorded_at: "2026-10-03T11:00:00Z",
                  views: 1000,
                  likes: 80,
                  comments: 10,
                  shares: 10,
                  watch_time_seconds: 9000,
                  followers_gained: 12,
                  affiliate_clicks: 8,
                  conversions: 3,
                  revenue: 20,
                  currency: "EUR",
                },
              ],
            },
          ],
        },
      ],
    });

    render(<ProjectPerformance project={project} />);

    expect(screen.getAllByText("1,000")).toHaveLength(2);
    expect(screen.getAllByText("10.0%")).toHaveLength(2);
    expect(screen.getAllByText("€20.00")).toHaveLength(2);
    expect(screen.getByText("€20.00 per 1,000 views")).toBeTruthy();
  });
});

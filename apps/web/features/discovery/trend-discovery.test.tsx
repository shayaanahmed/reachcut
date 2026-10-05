import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TrendDiscovery } from "./trend-discovery";

describe("trend discovery", () => {
  it("searches by topic and requires authorized import", async () => {
    const importSource = vi.fn().mockResolvedValue({ id: "project-1" });
    const loadOpportunities = vi.fn().mockResolvedValue({
      country: { code: "US", name: "United States" },
      query: "film editing",
      category: "movies",
      fetched_at: "2026-10-03T10:00:00Z",
      topics: [
        {
          title: "Major topic",
          approximate_traffic: "200K+",
          news_title: "Context",
          news_url: "https://news.example/story",
        },
      ],
      sources: [
        {
          id: "video-1",
          title: "Major interview",
          url: "https://youtube.com/watch?v=video-1",
          channel: "Publisher",
          thumbnail_url: null,
          duration_seconds: 1800,
          view_count: 100000,
          published_at: null,
          opportunity_type: "trending_interview",
          topic: "Major topic",
          is_upcoming: false,
          source_score: 94,
        },
      ],
      note: "Confirm media rights before importing.",
    });
    render(
      <TrendDiscovery
        onCreated={vi.fn()}
        loadOpportunities={loadOpportunities}
        importSource={importSource}
      />,
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Search by topic" }), {
      target: { value: "film editing" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Movies & TV" }));
    expect(await screen.findByText("Major interview")).toBeTruthy();
    expect(loadOpportunities).toHaveBeenCalledWith({
      query: "film editing",
      category: "movies",
    });
    fireEvent.click(screen.getByRole("button", { name: "Use video" }));

    const importButton = screen.getByRole("button", {
      name: "Import and open project",
    }) as HTMLButtonElement;
    expect(importButton).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(importButton);

    await waitFor(() =>
      expect(importSource).toHaveBeenCalledWith({
        title: "Major interview",
        url: "https://youtube.com/watch?v=video-1",
        authorization_confirmed: true,
      }),
    );
  });
});

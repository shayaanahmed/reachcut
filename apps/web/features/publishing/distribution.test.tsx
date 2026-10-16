import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { socialAccountSchema, projectSchema } from "../../lib/contracts";
import { DestinationSelector } from "./destination-selector";
import { BulkClipActions } from "./bulk-clip-actions";
import { insightPosts, summarizeInsights, viewsTimeline } from "./insight-data";

const date = "2026-10-10T10:00:00Z";
const account = socialAccountSchema.parse({
  id: "faith",
  platform: "instagram",
  label: "Faith IG",
  username: "faith",
  profile_url: null,
  default_hashtags: [],
  default_cta: "",
  default_campaign_url: null,
  currency: "EUR",
  connection_status: "connected",
  is_default: true,
  is_active: true,
  created_at: date,
  updated_at: date,
});
const art = { ...account, id: "art", label: "Art IG" };
const disconnected = {
  ...account,
  id: "offline",
  label: "Offline IG",
  connection_status: "disconnected",
};
const group = {
  id: "religious",
  name: "Religious",
  description: "Faith",
  account_ids: ["faith", "offline"],
};
const plan = {
  schema_version: "1.0",
  source: { start_seconds: 0, end_seconds: 30 },
  scores: {
    overall: 80,
    hook: 80,
    clarity: 80,
    payoff: 80,
    visual_interest: 80,
  },
  rationale: "A useful moment",
  suggested_title: "Useful clip",
  hook: null,
  caption_style: "clean",
  emphasis: [],
  effects: [],
  cta: null,
};
const metric = {
  id: 1,
  recorded_at: date,
  views: 100,
  likes: 10,
  comments: 1,
  shares: 1,
  watch_time_seconds: null,
  followers_gained: 0,
  affiliate_clicks: 0,
  conversions: 0,
  revenue: 5,
  currency: "EUR",
};
const post = {
  id: "post",
  platform: "instagram",
  status: "published",
  post_url: "https://www.instagram.com/reel/example/",
  title: "Post",
  description: "",
  published_at: date,
  created_at: date,
  social_account_id: "faith",
  metric_snapshots: [
    metric,
    { ...metric, id: 2, views: 150, recorded_at: "2026-10-12T10:00:00Z" },
  ],
};
const project = projectSchema.parse({
  id: "project",
  title: "Project",
  original_filename: "source.mp4",
  status: "review",
  duration_seconds: 60,
  authorization_confirmed_at: date,
  created_at: date,
  stages: [],
  clips: [
    {
      id: "one",
      approval_status: "approved",
      preview_path: null,
      final_path: "/final.mp4",
      plan,
      publications: [post],
    },
    {
      id: "two",
      approval_status: "pending",
      preview_path: null,
      final_path: null,
      plan: { ...plan, suggested_title: "Second clip" },
      publications: [],
    },
  ],
});
afterEach(cleanup);

describe("distribution destinations", () => {
  it("chooses only connected group members, never other accounts on the same platform", () => {
    const change = vi.fn();
    render(
      <DestinationSelector
        accounts={[account, art, disconnected]}
        groups={[group]}
        selected={[]}
        onChange={change}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Social group" }));
    fireEvent.change(screen.getByLabelText("Social group"), {
      target: { value: "religious" },
    });
    expect(change).toHaveBeenLastCalledWith(["faith"]);
    expect(screen.getByRole("checkbox", { name: /Offline IG/ })).toBeDisabled();
  });
  it("publishes all ready clips only to explicitly chosen destinations", async () => {
    const publish = vi.fn().mockResolvedValue(undefined);
    const approve = vi.fn().mockResolvedValue(project);
    render(
      <BulkClipActions
        project={project}
        accounts={[account, art]}
        groups={[group]}
        pending={false}
        onApprove={approve}
        onRender={vi.fn()}
        onPublish={publish}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Publish all ready (1)" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /Faith IG/ }));
    fireEvent.click(
      screen.getByRole("button", { name: "Publish all ready (1)" }),
    );
    await waitFor(() =>
      expect(publish).toHaveBeenCalledWith("project", ["one"], ["faith"]),
    );
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Select all 2 clips/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Approve selected" }));
    await waitFor(() =>
      expect(approve).toHaveBeenCalledWith("project", ["one", "two"]),
    );
  });
});
describe("insight calculations", () => {
  it("uses latest cumulative values, carries history forward, and never sums snapshots", () => {
    const rows = insightPosts([project]);
    const totals = summarizeInsights(rows);
    expect(totals.views).toBe(150);
    expect(totals.revenue).toEqual({ EUR: 5 });
    const points = viewsTimeline(
      rows,
      new Date("2026-10-10T00:00:00Z"),
      new Date("2026-10-13T23:59:59Z"),
    );
    expect(points.map((p) => p.views)).toEqual([100, 100, 150, 150]);
  });
  it("keeps mixed currencies separate and excludes failed posts", () => {
    const second = structuredClone(project);
    second.clips[0].publications[0].metric_snapshots = [
      { ...metric, currency: "USD", revenue: 8 },
    ];
    second.clips[1].publications = [
      { ...second.clips[0].publications[0], status: "failed" },
    ];
    const rows = insightPosts([project, second]);
    expect(rows).toHaveLength(2);
    expect(summarizeInsights(rows).revenue).toEqual({ EUR: 5, USD: 8 });
  });
});

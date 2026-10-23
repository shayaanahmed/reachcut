import { expect, test } from "@playwright/test";

const date = "2026-10-16T10:00:00Z";
const account = {
  id: "faith",
  platform: "instagram",
  label: "Faith channel",
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
};
const art = { ...account, id: "art", label: "Art channel", username: "art" };
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
  rationale: "A self-contained idea",
  suggested_title: "A useful idea",
  hook: null,
  caption_style: "clean",
  emphasis: [],
  effects: [],
  cta: null,
};
const metric = {
  id: 1,
  recorded_at: date,
  views: 1234,
  likes: 100,
  comments: 10,
  shares: 5,
  watch_time_seconds: null,
  followers_gained: 0,
  affiliate_clicks: 0,
  conversions: 0,
  revenue: 0,
  currency: "EUR",
};
const project = {
  id: "project",
  title: "Faith project",
  original_filename: "source.mp4",
  status: "review",
  duration_seconds: 90,
  authorization_confirmed_at: date,
  created_at: date,
  stages: [],
  clips: [
    {
      id: "clip-one",
      approval_status: "approved",
      preview_path: null,
      final_path: "/final.mp4",
      plan,
      publications: [],
    },
    {
      id: "clip-two",
      approval_status: "pending",
      preview_path: null,
      final_path: null,
      plan: { ...plan, suggested_title: "Second idea" },
      publications: [],
    },
  ],
};

test("manage groups and publish a selection to the intended channels", async ({
  page,
}) => {
  let groups: {
    id: string;
    name: string;
    description: string;
    account_ids: string[];
  }[] = [];
  await page.route("**/api/social-account-groups**", async (route) => {
    const method = route.request().method();
    if (method === "POST") {
      groups = [{ ...route.request().postDataJSON(), id: "religious" }];
      await route.fulfill({ status: 201, json: groups[0] });
    } else if (method === "PUT") {
      groups = [{ ...route.request().postDataJSON(), id: "religious" }];
      await route.fulfill({ json: groups[0] });
    } else if (method === "DELETE") {
      groups = [];
      await route.fulfill({ status: 204 });
    } else await route.fulfill({ json: groups });
  });
  await page.route("**/api/social-accounts", (route) =>
    route.fulfill({ json: [account, art] }),
  );
  await page.route("**/api/social-accounts/readiness", (route) =>
    route.fulfill({
      json: [account, art].map((a) => ({
        account_id: a.id,
        platform: a.platform,
        publishing_ready: true,
        credentials_available: true,
        provider_configured: true,
        issues: [],
      })),
    }),
  );
  await page.route("**/api/publishing/capabilities", (route) =>
    route.fulfill({
      json: { configured_platforms: ["instagram"], provider_setup: [] },
    }),
  );
  await page.route("**/api/projects", (route) =>
    route.fulfill({ json: [project] }),
  );
  await page.route("**/api/projects/project/clip-types", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto("/settings/accounts");
  await page.getByRole("button", { name: "New group" }).click();
  await page.getByLabel("Group name", { exact: true }).fill("Religious");
  await page.getByRole("checkbox", { name: /Faith channel/ }).check();
  await page.getByRole("button", { name: "Save group", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Religious", exact: true }),
  ).toBeVisible();
  expect(groups[0].account_ids).toEqual(["faith"]);
  await page.getByRole("button", { name: "Edit group", exact: true }).click();
  await page.getByLabel("Group name", { exact: true }).fill("Faith & learning");
  await page.getByRole("button", { name: "Save group", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Faith & learning", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name: "Publishing", exact: true })
    .click();
  await page.getByRole("checkbox", { name: /Select all 2 clips/ }).check();
  await page.getByRole("button", { name: "Social group", exact: true }).click();
  await page
    .getByLabel("Social group", { exact: true })
    .selectOption("religious");
  await expect(
    page.getByRole("checkbox", { name: /Faith channel/ }),
  ).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: /Art channel/ }),
  ).not.toBeChecked();
  await page.route("**/api/projects/project/publish-batch", async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      clip_ids: ["clip-one", "clip-two"],
      account_ids: ["faith"],
    });
    await route.fulfill({
      status: 202,
      json: {
        project,
        queued: 1,
        skipped: [
          {
            clip_id: "clip-two",
            account_id: "faith",
            reason: "Approve this clip first",
          },
        ],
      },
    });
  });
  await page.getByRole("button", { name: /Publish selected/ }).click();
  await expect(page.getByRole("status")).toContainText(
    "1 posts queued · 0 existing posts updated · 1 skipped",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "/tmp/reachcut-publishing-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "/tmp/reachcut-publishing-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("insights preserve old metrics and skip disconnected accounts without dashboard alerts", async ({
  page,
}) => {
  const published = {
    id: "post",
    platform: "instagram",
    status: "published",
    post_url: "https://www.instagram.com/reel/example/",
    title: "A useful idea",
    description: "",
    published_at: date,
    created_at: date,
    social_account_id: "archived-account",
    account_label: "Old faith channel",
    account_username: "faith",
    metric_snapshots: [
      { ...metric, id: 0, views: 100, recorded_at: "2026-10-15T10:00:00Z" },
      metric,
    ],
  };
  const withPost = {
    ...project,
    clips: [{ ...project.clips[0], publications: [published] }],
  };
  let syncs = 0;
  await page.route("**/api/projects", (route) =>
    route.fulfill({ json: [withPost] }),
  );
  await page.route("**/api/projects/project/clip-types", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/social-accounts", (route) =>
    route.fulfill({ json: [account] }),
  );
  await page.route("**/api/social-accounts/readiness", (route) =>
    route.fulfill({
      json: [
        {
          account_id: "faith",
          platform: "instagram",
          publishing_ready: true,
          credentials_available: true,
          provider_configured: true,
          issues: [],
        },
      ],
    }),
  );
  await page.route("**/api/social-account-groups", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/publications/post/metrics/sync", (route) => {
    syncs++;
    return route.fulfill({
      status: 409,
      json: { detail: "publishing account is no longer connected" },
    });
  });
  await page.goto("/insights");
  await expect(
    page.getByRole("heading", { name: "Views & insights" }),
  ).toBeVisible();
  await page
    .getByText("Views over time · explore the trend chart", { exact: true })
    .click();
  await expect(
    page.getByRole("img", { name: /Cumulative views/ }),
  ).toBeVisible();
  const syncStatus = page.getByRole("group", { name: "Account sync status" });
  await syncStatus.locator("summary").click();
  await expect(syncStatus).toContainText("1 account sync issue need attention");
  await expect(
    page.locator(".insight-totals").getByText("1,234", { exact: true }),
  ).toBeVisible();
  expect(syncs).toBe(0);
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  await page.screenshot({
    path: "/tmp/reachcut-insights-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "/tmp/reachcut-insights-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("one failed metrics sync does not prevent another account from refreshing", async ({
  page,
}) => {
  const published = {
    id: "broken",
    platform: "instagram",
    status: "published",
    post_url: "https://www.instagram.com/reel/example/",
    title: "A useful idea",
    description: "",
    published_at: date,
    created_at: date,
    social_account_id: "faith",
    account_label: "Faith channel",
    metric_snapshots: [metric],
  };
  const withPosts = {
    ...project,
    clips: [
      {
        ...project.clips[0],
        publications: [
          published,
          {
            ...published,
            id: "healthy",
            social_account_id: "art",
            account_label: "Art channel",
          },
        ],
      },
    ],
  };
  const calls: string[] = [];
  await page.route("**/api/projects", (route) =>
    route.fulfill({ json: [withPosts] }),
  );
  await page.route("**/api/projects/project/clip-types", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/social-account-groups", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/social-accounts", (route) =>
    route.fulfill({ json: [account, art] }),
  );
  await page.route("**/api/social-accounts/readiness", (route) =>
    route.fulfill({
      json: [account, art].map((a) => ({
        account_id: a.id,
        platform: a.platform,
        publishing_ready: true,
        credentials_available: true,
        provider_configured: true,
        issues: [],
      })),
    }),
  );
  await page.route("**/api/publications/*/metrics/sync", (route) => {
    const id = route.request().url().includes("/broken/")
      ? "broken"
      : "healthy";
    calls.push(id);
    return id === "broken"
      ? route.fulfill({
          status: 502,
          json: { detail: "Authorization expired. Reconnect Faith channel." },
        })
      : route.fulfill({ json: withPosts });
  });
  await page.goto("/insights");
  await page
    .getByRole("group", { name: "Account sync status" })
    .locator("summary")
    .click();
  await expect(
    page.getByText("Authorization expired. Reconnect Faith channel.", {
      exact: false,
    }),
  ).toBeVisible();
  expect(calls).toEqual(["broken", "healthy"]);
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
});

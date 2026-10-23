import { expect, test } from "@playwright/test";

const date = "2026-10-23T10:00:00Z";
const posts = ["youtube", "instagram", "facebook"].map((platform, index) => ({
  id: `post-${platform}`,
  platform,
  status: "published",
  post_url: `https://example.com/${platform}`,
  title: "Reel 30 seconds",
  description: "Original caption",
  published_at: date,
  created_at: date,
  social_account_id: `account-${platform}`,
  account_label: `${platform} channel`,
  metric_snapshots: [
    {
      id: index + 1,
      recorded_at: date,
      views: (index + 1) * 100,
      likes: 10,
      comments: 2,
      shares: 3,
      watch_time_seconds: null,
      followers_gained: 0,
      affiliate_clicks: 0,
      conversions: 0,
      revenue: 0,
      currency: "EUR",
    },
  ],
}));
const project = {
  id: "project",
  title: "Soyos Studios",
  original_filename: "source.mp4",
  status: "complete",
  duration_seconds: 30,
  authorization_confirmed_at: date,
  created_at: date,
  stages: [],
  clips: [
    {
      id: "clip",
      approval_status: "approved",
      preview_path: null,
      final_path: "/final.mp4",
      plan: {
        schema_version: "1.0",
        source: { start_seconds: 0, end_seconds: 30 },
        scores: {
          overall: 80,
          hook: 80,
          clarity: 80,
          payoff: 80,
          visual_interest: 80,
        },
        rationale: "Useful moment",
        suggested_title: "Reel 30 seconds",
        hashtags: [],
        hook: null,
        caption_style: "clean",
        emphasis: [],
        effects: [],
        cta: null,
      },
      publications: posts,
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json =
      path === "/api/projects"
        ? [project]
        : path === "/api/projects/project"
          ? project
          : path === "/api/projects/project/workflows"
            ? { speech_available: false, runs: [] }
            : path.endsWith("/management")
              ? {
                  capabilities: {
                    update: !path.includes("instagram"),
                    delete: true,
                    title: path.includes("youtube"),
                    explanation: "Manage the original post.",
                  },
                  suggested: {
                    title: "Improved title",
                    description: "New audience-focused caption #Useful",
                  },
                  needs_update: true,
                  operation: null,
                  history: [],
                }
              : path === "/api/social-accounts"
                ? []
                : path.includes("/metrics/sync")
                  ? project
                  : path === "/api/publishing/capabilities"
                    ? {
                        configured_platforms: [
                          "youtube",
                          "instagram",
                          "facebook",
                        ],
                        provider_setup: [],
                      }
                    : [];
    await route.fulfill({ json });
  });
});

test("groups three destinations into one expandable clip and separates growth", async ({
  page,
}) => {
  await page.goto("/insights");
  const groups = page
    .getByRole("region", { name: "Post performance by clip" })
    .locator("details.clip-insight-group");
  await expect(groups).toHaveCount(1);
  await expect(groups.locator("summary")).toContainText("600");
  await expect(groups.getByRole("table")).not.toBeVisible();
  await groups.locator("summary").click();
  await expect(groups.getByRole("row")).toHaveCount(4);
  await expect(
    page.getByRole("heading", { name: "Growth experiments" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("main").getByRole("link", { name: "Growth & experiments" }),
  ).toHaveAttribute("href", "/growth");
  await page.screenshot({ path: "/tmp/reachcut-insights.png", fullPage: true });
});

test("offers latest copy and differentiates platform deletion from local removal", async ({
  page,
}) => {
  await page.goto("/publishing/posts?clip=clip");
  const group = page.locator("details.clip-insight-group");
  await expect(group).toHaveCount(1);
  await group.locator(":scope > summary").click();
  const youtube = page.getByRole("article", {
    name: "youtube youtube channel",
  });
  await youtube.getByText("Edit publishing details", { exact: true }).click();
  await expect(youtube.getByLabel("Title")).toHaveValue("Improved title");
  await expect(youtube.getByLabel("Caption / description")).toHaveValue(
    "New audience-focused caption #Useful",
  );
  await youtube.getByRole("button", { name: "Delete from youtube" }).click();
  await expect(
    youtube.getByRole("group", { name: "Confirm post action" }),
  ).toContainText("Delete the actual youtube post?");
  await youtube.getByRole("button", { name: "Keep it" }).click();
  await youtube.getByRole("button", { name: "Remove local record" }).click();
  await expect(
    youtube.getByRole("group", { name: "Confirm post action" }),
  ).toContainText("original platform post will remain");
  const instagram = page.getByRole("article", {
    name: "instagram instagram channel",
  });
  await instagram.getByText("Edit publishing details", { exact: true }).click();
  await expect(
    instagram.getByRole("button", { name: "Update existing post" }),
  ).toBeDisabled();
  await page.screenshot({
    path: "/tmp/reachcut-post-board.png",
    fullPage: true,
  });
});

test("keeps publishing and grouped insights within a mobile viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of [
    "/",
    "/publishing",
    "/insights",
    "/growth",
    "/publishing/posts",
  ]) {
    await page.goto(path);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByText("Loading insights…")).toHaveCount(0);
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
      path,
    ).toBe(true);
  }
  await page.screenshot({
    path: "/tmp/reachcut-posts-mobile.png",
    fullPage: true,
  });
});

test("offers independent source workflows and submits a selected language version", async ({
  page,
}) => {
  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/projects/project/workflows", async (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: { speech_available: false, runs: [] } });
    const body = route.request().postData()!;
    const payload = body.match(/name="payload"\r\n\r\n([^\r]+)/)![1];
    submitted = JSON.parse(payload);
    await route.fulfill({
      status: 202,
      json: {
        ...submitted,
        id: "run",
        source_project_id: "project",
        source_title: project.title,
        target_project_id: "language-output",
        status: "queued",
        error: null,
        created_at: date,
        started_at: null,
        finished_at: null,
      },
    });
  });
  await page.goto("/projects/project");
  const workflows = page.getByRole("region", {
    name: "Source video workflows",
  });
  await expect(workflows.getByRole("tab")).toHaveCount(4);
  await workflows
    .getByRole("tab", { name: "Refresh publishing details" })
    .click();
  await expect(workflows.getByText("Existing clips to refresh")).toBeVisible();
  await workflows.getByRole("tab", { name: "Create language version" }).click();
  await workflows.getByLabel("Target language").selectOption("vi");
  await expect(
    workflows.getByLabel("Spoken subtitles", { exact: true }),
  ).toBeDisabled();
  await workflows.getByLabel("Reel 30 seconds", { exact: true }).check();
  await workflows
    .getByRole("button", { name: "Create language version", exact: true })
    .click();
  await expect(workflows.getByRole("status")).toContainText("Workflow queued");
  expect(submitted).toMatchObject({
    kind: "language",
    target_language: "vi",
    clip_ids: ["clip"],
    scopes: ["metadata"],
  });
  await page.screenshot({
    path: "/tmp/reachcut-source-workflows.png",
    fullPage: true,
  });
});

test("keeps a latest draft editable while showing a YouTube reconnect action", async ({
  page,
}) => {
  await page.route("**/api/publications/post-youtube/management", (route) =>
    route.fulfill({
      json: {
        capabilities: {
          update: true,
          delete: true,
          title: true,
          explanation: "Update the original post.",
          reconnect_required: true,
          connection_issue:
            "Reconnect this channel for post-management permission.",
        },
        suggested: {
          title: "Latest draft",
          description: "Latest copy #Github",
        },
        needs_update: true,
        operation: null,
        history: [],
      },
    }),
  );
  await page.goto("/publishing/posts?clip=clip");
  await page.locator("details.clip-insight-group > summary").click();
  const youtube = page.getByRole("article", {
    name: "youtube youtube channel",
  });
  await expect(
    youtube.getByRole("link", { name: "Reconnect youtube account" }),
  ).toBeVisible();
  await youtube.getByText("Edit publishing details", { exact: true }).click();
  await expect(youtube.getByLabel("Title")).toHaveValue("Latest draft");
  await youtube.getByLabel("Title").fill("My saved draft");
  await youtube.getByRole("button", { name: "Check connection again" }).click();
  await expect(youtube.getByLabel("Title")).toHaveValue("My saved draft");
  await expect(
    youtube.getByRole("button", { name: "Update existing post", exact: true }),
  ).toBeDisabled();
});

const composerAccounts = ["youtube", "instagram"].map((platform) => ({
  id: `account-${platform}`,
  platform,
  label: `${platform} channel`,
  username: "insightinseconds",
  profile_url: null,
  default_hashtags: [],
  default_cta: "",
  default_campaign_url: null,
  currency: "EUR",
  connection_status: "connected",
  is_default: platform === "youtube",
  is_active: true,
  created_at: date,
  updated_at: date,
}));
const composerCopy = ["youtube", "instagram"].map((platform) => ({
  platform,
  title: "Improved title",
  caption: "New audience-focused caption #Useful",
  cover_text: "Useful",
  hashtags: [],
}));

test("explains mixed updates, reports each destination, and keeps Instagram-only idle after reload", async ({
  page,
}) => {
  const saved = structuredClone(project);
  const mutations: string[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/projects/project") return route.fulfill({ json: saved });
    if (path === "/api/social-accounts")
      return route.fulfill({ json: composerAccounts });
    if (path.endsWith("/publishing-copy"))
      return route.fulfill({
        json: { packages: composerCopy, hashtag_notice: null },
      });
    if (path === "/api/social-account-groups")
      return route.fulfill({
        json: [
          {
            id: "group",
            name: "Insight in Seconds",
            description: "",
            account_ids: composerAccounts.map((a) => a.id),
          },
        ],
      });
    if (path.endsWith("/management"))
      return route.fulfill({
        json: {
          capabilities: {
            update: !path.includes("instagram"),
            delete: true,
            title: path.includes("youtube"),
            explanation: path.includes("instagram")
              ? "Instagram caption editing is unavailable through this integration. Open Instagram to edit it."
              : "Update the existing YouTube post.",
          },
          suggested: {
            title: "Improved title",
            description: composerCopy[0].caption,
          },
          needs_update: true,
          operation: null,
          history: [],
        },
      });
    if (route.request().method() === "PUT") {
      mutations.push(path);
      expect(path).toBe("/api/publications/post-youtube/remote");
      saved.clips[0].publications[0].title = "Improved title";
      saved.clips[0].publications[0].description = composerCopy[0].caption;
      return route.fulfill({ json: saved });
    }
    return route.fallback();
  });
  await page.goto("/projects/project/clips/clip/publish");
  await page.getByLabel("Publishing social group").selectOption("group");
  const actions = page.getByRole("region", {
    name: "Actions for selected destinations",
  });
  await expect(actions).toContainText("Open Instagram to edit it");
  await expect(page.getByLabel("Suggested title")).toHaveValue(
    "Improved title",
  );
  await expect(
    page.getByLabel("Description and hashtags", { exact: true }),
  ).toHaveValue(composerCopy[0].caption);
  await expect(
    actions.getByRole("link", { name: "Open original Instagram post" }),
  ).toHaveAttribute("href", "https://example.com/instagram");
  await page.getByRole("button", { name: /Update 1 existing post/ }).click();
  const results = page.getByRole("region", { name: "Publishing results" });
  await expect(results).toContainText("youtube channel · updated");
  await expect(results).toContainText("instagram channel · Edit on platform");
  expect(mutations).toHaveLength(1);
  expect(saved.clips[0].publications[1].title).toBe("Reel 30 seconds");
  await page.reload();
  await page.getByLabel("Publishing platform").selectOption("instagram");
  const idle = page.getByRole("button", {
    name: "No automatic actions available",
  });
  await expect(idle).toBeDisabled();
  await expect(idle).toHaveAttribute("aria-busy", "false");
  await expect(idle).toHaveCSS("cursor", "not-allowed");
  await expect(
    page.getByRole("button", { name: "Copy latest caption", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/reachcut-instagram-idle.png",
    fullPage: true,
  });
});

test("queues new destinations independently and does not duplicate a successful upload on retry", async ({
  page,
}) => {
  const saved = structuredClone(project);
  saved.clips[0].publications = [];
  const attempts: string[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/projects/project") return route.fulfill({ json: saved });
    if (path === "/api/social-accounts")
      return route.fulfill({ json: composerAccounts });
    if (path.endsWith("/publishing-copy"))
      return route.fulfill({
        json: { packages: composerCopy, hashtag_notice: null },
      });
    if (path === "/api/social-account-groups")
      return route.fulfill({
        json: [
          {
            id: "group",
            name: "Insight in Seconds",
            description: "",
            account_ids: composerAccounts.map((a) => a.id),
          },
        ],
      });
    if (path === "/api/clips/clip/publish-batch") {
      const request = route.request().postDataJSON().publications;
      expect(request).toHaveLength(1);
      attempts.push(request[0].social_account_id);
      if (request[0].social_account_id === "account-instagram")
        return route.fulfill({
          status: 409,
          json: { detail: "Instagram upload unavailable; reconnect." },
        });
      saved.clips[0].publications = [{ ...posts[0], status: "queued" }];
      return route.fulfill({ json: saved });
    }
    return route.fallback();
  });
  await page.goto("/projects/project/clips/clip/publish");
  await page.getByLabel("Publishing social group").selectOption("group");
  await page.getByRole("button", { name: /Publish to 2 destinations/ }).click();
  const results = page.getByRole("region", { name: "Publishing results" });
  await expect(results).toContainText("youtube channel · queued");
  await expect(results).toContainText("instagram channel · failed");
  await page.getByRole("button", { name: /Publish to 1 destinations/ }).click();
  await expect(results).toContainText("youtube channel · blocked");
  expect(attempts.filter((id) => id === "account-youtube")).toHaveLength(1);
  expect(attempts.filter((id) => id === "account-instagram")).toHaveLength(2);
});

test("disables unauthorized Instagram deletion and explains the separate authorization", async ({
  page,
}) => {
  const writes: string[] = [];
  await page.route("**/api/publications/post-instagram/**", async (route) => {
    if (route.request().method() !== "GET") {
      writes.push(route.request().method());
      return route.fulfill({
        status: 409,
        json: { detail: "Deletion permission missing" },
      });
    }
    await route.fulfill({
      json: {
        capabilities: {
          update: false,
          delete: false,
          title: false,
          explanation: "Edit this caption on Instagram.",
          deletion_issue:
            "Instagram deletion requires instagram_manage_contents and a Facebook User access token. Add this to the Meta login configuration, then reconnect.",
          deletion_reconnect_required: true,
        },
        suggested: { title: "Latest", description: "Latest caption" },
        needs_update: true,
        operation: {
          state: "failed",
          action: "delete",
          error: "Old provider error",
        },
        history: [],
      },
    });
  });
  await page.goto("/publishing/posts?clip=clip");
  await page.locator("details.clip-insight-group > summary").click();
  const instagram = page.getByRole("article", {
    name: "instagram instagram channel",
  });
  await expect(
    instagram.getByRole("button", { name: "Delete from instagram" }),
  ).toBeDisabled();
  await expect(
    instagram.getByText("Deletion needs setup", { exact: true }),
  ).toBeVisible();
  await expect(
    instagram.getByRole("link", { name: "Reconnect for instagram deletion" }),
  ).toHaveAttribute("href", "/api/social-accounts/account-instagram/connect");
  await expect(instagram.getByRole("alert")).not.toContainText(
    "Old provider error",
  );
  expect(writes).toEqual([]);
});

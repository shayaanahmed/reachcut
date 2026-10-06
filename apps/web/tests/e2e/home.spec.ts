import { expect, test } from "@playwright/test";

test("shows the tool dashboard and local project workflow", async ({
  page,
}) => {
  await page.route("**/api/projects", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Content command center" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "New project" })).toBeVisible();
  await expect(page.getByText("Local processing")).toBeVisible();
});

test("moves a finished clip from the core studio into publishing", async ({
  page,
}) => {
  await page.setViewportSize({ width: 902, height: 808 });
  await page.route("**/api/projects/project-1", (route) =>
    route.fulfill({
      json: {
        id: "project-1",
        title: "Creator interview",
        original_filename: "interview.mp4",
        status: "review",
        duration_seconds: 90,
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
              source: { start_seconds: 2, end_seconds: 32 },
              scores: {
                overall: 88,
                hook: 91,
                clarity: 84,
                payoff: 89,
                visual_interest: 82,
              },
              rationale: "A clear hook with a useful payoff.",
              suggested_title: "The advice every creator needs",
              hashtags: ["#CreatorTips"],
              hook: null,
              caption_style: "clean",
              emphasis: [],
              effects: [],
              cta: null,
            },
            publications: [],
          },
        ],
      },
    }),
  );
  await page.route("**/api/social-accounts", (route) =>
    route.fulfill({
      json: [
        {
          id: "account-1",
          platform: "youtube",
          label: "Main YouTube",
          username: "creator",
          profile_url: null,
          default_hashtags: ["#Shorts"],
          default_cta: "Subscribe for more",
          default_campaign_url: null,
          currency: "EUR",
          connection_status: "connected",
          is_default: true,
          is_active: true,
          created_at: "2026-10-02T10:00:00Z",
          updated_at: "2026-10-02T10:00:00Z",
        },
      ],
    }),
  );

  await page.goto("/projects/project-1/clips/clip-1");

  await expect(
    page.getByRole("heading", { name: "Your publishing master is ready" }),
  ).toBeVisible();
  await expect(page.getByText("CORE WORKSPACE · CLIP STUDIO")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Publish and measure" }),
  ).toHaveCount(0);

  await page.getByRole("button", { name: /Assets/ }).click();
  const controlsBox = await page.locator(".studio-controls").boundingBox();
  const assetsBox = await page.locator(".assets-panel").boundingBox();
  expect(controlsBox).not.toBeNull();
  expect(assetsBox).not.toBeNull();
  expect(Math.abs(assetsBox!.y - controlsBox!.y)).toBeLessThan(3);
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);

  await page.getByRole("link", { name: /Open publishing/ }).click();
  await expect(page).toHaveURL(
    /\/projects\/project-1\/clips\/clip-1\/publish$/,
  );
  await expect(
    page.getByRole("heading", { name: "Publish your finished clip" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Publish and measure" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Main YouTube/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Publish to YouTube Shorts" }),
  ).toBeEnabled();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
});

test("keeps the primary product pages inside tablet and mobile viewports", async ({
  page,
}) => {
  await page.route("**/api/projects", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/publishing/capabilities", (route) =>
    route.fulfill({
      json: {
        youtube_configured: true,
        automatic_platforms: ["youtube"],
        configured_platforms: ["youtube"],
      },
    }),
  );
  await page.route("**/api/social-accounts/readiness", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/social-accounts", (route) =>
    route.fulfill({ json: [] }),
  );

  for (const viewport of [
    { width: 902, height: 808 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    for (const path of [
      "/",
      "/projects",
      "/projects/new",
      "/settings/accounts",
    ]) {
      await page.goto(path);
      await expect(page.locator("main")).toBeVisible();
      expect(
        await page.evaluate(
          () =>
            document.documentElement.scrollWidth <=
            document.documentElement.clientWidth,
        ),
        `${path} overflowed at ${viewport.width}px`,
      ).toBe(true);
    }
  }
});

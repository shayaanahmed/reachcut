import { expect, test } from "@playwright/test";

const date = "2026-10-15T10:00:00Z";
const queuedProject = {
  id: "project-queued",
  title: "Founder interview",
  original_filename: "Pending URL import",
  status: "queued",
  duration_seconds: null,
  storage_bytes: 0,
  authorization_confirmed_at: date,
  created_at: date,
  stages: [],
  clips: [],
  job: {
    status: "queued",
    phase: "Waiting to start",
    source_url: "https://youtube.com/watch?v=abc",
    error: null,
    enqueued_at: date,
  },
};
const account = {
  id: "account-1",
  platform: "youtube",
  label: "Main channel",
  username: "creator",
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

test("adds a URL source and configures an automation while its project waits", async ({
  page,
}) => {
  let created = false;
  let pipeline: Record<string, unknown> | null = null;
  await page.route("**/api/projects", (route) =>
    route.fulfill({ json: created ? [queuedProject] : [] }),
  );
  await page.route("**/api/projects/import-url", async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({
      title: "Founder interview",
      authorization_confirmed: true,
    });
    created = true;
    await route.fulfill({
      status: 201,
      json: queuedProject,
      headers: { "Access-Control-Allow-Origin": "*" },
    });
  });
  await page.route("**/api/social-accounts", (route) =>
    route.fulfill({ json: [account] }),
  );
  await page.route("**/api/automations", async (route) => {
    if (route.request().method() === "POST") {
      const request = route.request().postDataJSON();
      expect(request.project_id).toBe(queuedProject.id);
      expect(request.clip_selection).toBe("all");
      pipeline = {
        ...request,
        id: "automation-1",
        status: "active",
        auto_approve: true,
        last_run_at: null,
        last_error: null,
        created_at: date,
        updated_at: date,
      };
      await route.fulfill({ status: 201, json: pipeline });
    } else await route.fulfill({ json: pipeline ? [pipeline] : [] });
  });
  await page.goto("/automations");
  await page.getByRole("button", { name: "From URL", exact: true }).click();
  await page
    .getByLabel("Public video URL")
    .fill("https://youtube.com/watch?v=abc");
  await page
    .getByLabel("Project name", { exact: true })
    .fill("Founder interview");
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Create project & add to queue" })
    .click();
  await expect(page.getByLabel("Source project")).toHaveValue(queuedProject.id);
  await expect(page.getByLabel("Queue position 1")).toBeVisible();
  await page.getByRole("button", { name: "Continue →" }).click();
  await page.getByRole("button", { name: /All matches/ }).click();
  await page.getByRole("button", { name: "Continue →" }).click();
  await page.getByRole("button", { name: /Main channel/ }).click();
  await page.getByRole("button", { name: "Continue →" }).click();
  await page.getByLabel("Pipeline name").fill("Interview highlights");
  await page.getByLabel("First run").fill("2026-10-16T12:00");
  await page.getByRole("button", { name: "Activate pipeline" }).click();
  await expect(
    page.getByRole("heading", { name: "Interview highlights" }),
  ).toBeVisible();
  await expect(
    page.getByText("waiting for source", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "/tmp/reachcut-automation-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Upload video", exact: true }).click();
  await expect(page.getByLabel("Source video")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "/tmp/reachcut-automation-mobile.png",
    fullPage: true,
  });
});

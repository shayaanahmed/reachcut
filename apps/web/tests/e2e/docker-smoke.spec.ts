import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

// These checks write only to the explicitly selected disposable Docker stack.
test.skip(
  process.env.PLAYWRIGHT_BASE_URL !== "http://127.0.0.1:3300",
  "Requires the isolated compose.testing.yaml stack",
);
test.describe.configure({ mode: "serial" });

test("real Docker upload, publishing records, metrics, validation and cleanup", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(60_000);
  const fixture = testInfo.outputPath("existing-video.mp4");
  const require = createRequire(__filename);
  execFileSync(require("ffmpeg-static"), [
    "-hide_banner",
    "-loglevel",
    "error",
    "-f",
    "lavfi",
    "-i",
    "color=c=navy:s=640x360:r=10:d=31",
    "-f",
    "lavfi",
    "-i",
    "sine=frequency=440:duration=31",
    "-c:v",
    "libx264",
    "-preset",
    "ultrafast",
    "-c:a",
    "aac",
    "-shortest",
    "-y",
    fixture,
  ]);
  const settings = await (await request.get("/api/settings")).json();
  const projectIds: string[] = [];
  let groupId: string | undefined;
  try {
    expect(
      (
        await request.put("/api/settings", {
          data: { ...settings, automatic_growth: false },
        })
      ).ok(),
    ).toBe(true);
    expect((await request.get("/api/settings")).ok()).toBe(true);
    // Real browser upload traverses the configured direct API URL and CORS.
    await page.goto("/studio");
    await page.getByLabel("Finished video (MP4)").setInputFiles(fixture);
    await page.getByRole("checkbox").check();
    const uploaded = page.waitForResponse(
      (response) =>
        response.url().endsWith("/projects/upload-for-publishing") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: /Upload/ }).click();
    const response = await uploaded;
    expect(response.status()).toBe(201);
    const project = await response.json();
    projectIds.push(project.id);
    const clip = project.clips[0];
    await expect(page).toHaveURL(
      new RegExp(`/projects/${project.id}/clips/${clip.id}$`),
    );
    await expect(
      page.getByRole("heading", { name: "Your publishing master is ready" }),
    ).toBeVisible();
    const final = await request.get(`/api/clips/${clip.id}/final`);
    expect(final.ok()).toBe(true);
    expect(await final.body()).toEqual(readFileSync(fixture));
    expect(
      (
        await request.get(`/api/clips/${clip.id}/final`, {
          headers: { Range: "bytes=0-15" },
        })
      ).status(),
    ).toBe(206);
    expect(
      (
        await request.put(`/api/projects/${project.id}`, {
          data: { title: " \t " },
        })
      ).status(),
    ).toBe(422);
    expect(
      (await (await request.get(`/api/projects/${project.id}`)).json()).title,
    ).toBe(project.title);
    expect(
      (
        await request.put(`/api/projects/${project.id}`, {
          data: { title: "Renamed audit video" },
        })
      ).ok(),
    ).toBe(true);
    const draft = await (
      await request.get(`/api/clips/${clip.id}/publishing-copy`)
    ).json();
    expect(draft.packages.length).toBeGreaterThan(0);
    expect(
      (await request.get(`/api/projects/${project.id}/workflows`)).ok(),
    ).toBe(true);
    expect(
      (await request.get(`/api/projects/${project.id}/quality`)).ok(),
    ).toBe(true);
    // Record an already published post locally; no remote publication is sent.
    const tracked = await request.post(`/api/clips/${clip.id}/publications`, {
      data: {
        platform: "youtube",
        status: "published",
        post_url: "https://example.com/audit-post",
        title: "Audit record",
      },
    });
    expect(tracked.ok()).toBe(true);
    const publication = (await tracked.json()).clips[0].publications[0];
    expect(
      (
        await request.post(`/api/publications/${publication.id}/metrics`, {
          data: { views: 321, likes: 12 },
        })
      ).ok(),
    ).toBe(true);
    expect(
      (
        await request.post(`/api/publications/${publication.id}/metrics`, {
          data: { views: -1 },
        })
      ).status(),
    ).toBe(422);
    await page.goto("/insights");
    await expect(
      page.locator(".insight-totals").getByText("321", { exact: true }),
    ).toBeVisible();
    expect(
      (await request.delete(`/api/publications/${publication.id}`)).ok(),
    ).toBe(true);
    const group = await request.post("/api/social-account-groups", {
      data: { name: `Audit ${project.id}`, account_ids: [] },
    });
    expect(group.status()).toBe(201);
    groupId = (await group.json()).id;
    expect(
      (
        await request.post("/api/social-account-groups", {
          data: { name: `Audit ${project.id}`, account_ids: [] },
        })
      ).status(),
    ).toBe(409);
    expect(
      (
        await request.put(`/api/social-account-groups/${groupId}`, {
          data: { name: `Renamed ${project.id}`, account_ids: [] },
        })
      ).ok(),
    ).toBe(true);
    expect((await request.get("/api/automations")).ok()).toBe(true);
    expect(
      (await request.post("/api/automations", { data: {} })).status(),
    ).toBe(422);
    const invalidUpload = await request.post(
      "http://127.0.0.1:8300/api/projects/upload-for-publishing",
      {
        multipart: {
          title: "Invalid media",
          authorization_confirmed: "true",
          media: {
            name: "invalid.mp4",
            mimeType: "video/mp4",
            buffer: Buffer.from("not video"),
          },
        },
      },
    );
    expect(invalidUpload.status()).toBe(415);
  } finally {
    if (groupId)
      expect(
        (
          await request.delete(`/api/social-account-groups/${groupId}`)
        ).status(),
      ).toBe(204);
    for (const id of projectIds) {
      expect((await request.delete(`/api/projects/${id}`)).status()).toBe(204);
      expect((await request.get(`/api/projects/${id}`)).status()).toBe(404);
    }
    expect((await request.put("/api/settings", { data: settings })).ok()).toBe(
      true,
    );
  }
});

test("real Docker pages and existing frame assets work on desktop and mobile", async ({
  page,
  request,
}) => {
  test.setTimeout(90_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const path of [
      "/",
      "/projects",
      "/projects/new",
      "/studio",
      "/publishing",
      "/publishing/posts",
      "/insights",
      "/growth",
      "/created",
      "/stories",
      "/labs/ai-scenes",
      "/frames",
      "/automations",
      "/settings/accounts",
      "/settings/general",
    ]) {
      const response = await page.goto(path);
      expect(response?.status(), path).toBeLessThan(400);
      await expect(page.locator("main")).toBeVisible();
      await expect(page.locator("main h1")).toBeVisible();
      expect(
        await page.evaluate(
          () =>
            document.documentElement.scrollWidth <=
            document.documentElement.clientWidth,
        ),
        `${path} at ${width}px`,
      ).toBe(true);
    }
  }
  expect(errors).toEqual([]);
  const frames = await (await request.get("/api/short-studio/frames")).json();
  expect(frames.length).toBeGreaterThan(0);
  for (const frame of frames.slice(0, 2)) {
    const response = await request.get(
      `/api/short-studio/frames/${frame.id}/preview`,
    );
    expect(response.ok()).toBe(true);
    expect(response.headers()["content-type"]).toContain("image/png");
  }
});

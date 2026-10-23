import { expect, test } from "@playwright/test";
import catalog from "./fixtures/studio-frames.json";

const repo = "https://github.com/example/photos";
const sources = [
  {
    id: "docs",
    title: "Photo organizer documentation",
    url: repo,
    text: "Organize photographs into folders by date.",
    retrieved_at: "2026-10-18",
  },
];
const brief = {
  id: "brief-1",
  category: "github",
  subject: "example/photos",
  repo_url: repo,
  context: "",
  analysis: "Organize photos by date using a documented local tool.",
  notices: [],
  sources,
  storylines: [1, 2, 3].map((i) => ({
    id: `story-${i}`,
    title: `Find your photos again ${i}`,
    hook: "Where did your holiday photos go?",
    focus:
      "Start with a familiar messy folder, reveal the organizer and explain how to try it.",
    payoff: "You could organize a photo collection by date.",
    source_id: "docs",
  })),
};
const settings = {
  category: "tech",
  style: "demo",
  language: "en",
  duration: 30,
  narration_mode: "none",
  profile_id: "",
  engine: "qwen",
  model_size: "1.7B",
  delivery: "",
  pronunciations: {},
  audience: "Everyone",
  tone: "Clear",
  caption_font: "Bricolage Grotesque",
  accent: "#244FF5",
  destinations: [],
  allow_explanation_cards: true,
  max_attempts: 2,
  spend_limit_usd: 0,
};
const sequence = catalog.sequences[0];
const visuals = sequence.frames.map((kind, i) => ({
  section_id: `scene_${i + 1}`,
  kind: "illustration",
  role: ["hook", "purpose", "example", "how", "outcome", "cta"][i],
  heading: `Scene ${i + 1}`,
  body: "Your photos, easier to find",
  quote: "",
  source_id: "",
  art_prompt: "A conceptual stack of physical photos on a table.",
  frame: {
    ...catalog.frames.find((f) => f.id === kind)!.sample,
    duration_seconds: sequence.durations[i],
  },
}));
const script = {
  version: "1",
  sections: visuals.map((v) => ({
    id: v.section_id,
    heading: v.heading,
    text: "Organize your photographs into folders by date.",
    visual: "explanation",
    claims: [],
  })),
};

async function setup(page: import("@playwright/test").Page, completed = false) {
  let deleted = false;
  let category = "github";
  let state = {
    id: "short-1",
    topic: "Find your photos again",
    settings,
    sources,
    script,
    status: completed ? "review" : "draft",
    phase: "Review your storyboard",
    error: null,
    artifacts: {},
    has_output: completed,
    approved: false,
    script_issues: [],
    findings: [],
    usage: {},
    publication_project_id: null,
  };
  const detail = () => ({
    short: state,
    episode: {
      series: {
        id: category,
        name: category === "github" ? "Exciting GitHub repos" : "Tech tricks",
        purpose: "Useful discoveries",
        audience: "Everyone",
        artwork_mode: "ollama",
        headline_font: sequence.font,
        settings,
        thumbnail: {
          layout: "split",
          background: sequence.background,
          accent: sequence.accent,
          foreground: "#151426",
          label: "",
          headline_template: "{headline}",
        },
      },
      brief: { ...brief, series_id: category, angles: brief.storylines },
      angle: brief.storylines[0],
      style: {
        id: sequence.id,
        name: sequence.name,
        design: { reuse_background: false },
        beats: [],
      },
      plan: {
        title: state.topic,
        editorial_notes: [
          "Beat 3 repeats beat 2; consider a different example.",
        ],
        headline: "Find your photos again",
        script,
        visuals,
      },
      request_signature: "test",
    },
  });
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace(/^\/api/, "");
    const method = req.method();
    let body: unknown = {};
    if (
      path.includes("/preview") ||
      path.includes("/visuals/") ||
      path.endsWith("/thumbnail")
    )
      return route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="270" height="480"><rect width="270" height="480" fill="#244ff5"/><text x="20" y="240" fill="white">Scene preview</text></svg>',
      });
    if (path.endsWith("/player"))
      return route.fulfill({
        contentType: "text/html",
        body: '<button aria-label="Replay frame">Animated frame preview</button>',
      });
    if (path === "/shorts/providers")
      body = { narration: { connected: false, profiles: [], engines: [] } };
    else if (path === "/short-studio/frames") body = catalog.frames;
    else if (path === "/short-studio/sequences") body = catalog.sequences;
    else if (path === "/short-studio/ideas") {
      category = req.postDataJSON().category;
      body = {
        id: "ideas-job",
        kind: "ideas",
        status: "queued",
        phase: "Reading documentation",
      };
    } else if (path === "/short-studio/jobs/ideas-job")
      body = {
        id: "ideas-job",
        kind: "ideas",
        status: "ready",
        phase: "Choose a storyline",
        brief: {
          ...brief,
          category,
          repo_url: category === "github" ? repo : "",
        },
        short_id: "",
      };
    else if (path === "/short-studio/storyboards")
      body = {
        id: "plan-job",
        kind: "storyboard",
        status: "queued",
        phase: "Writing scenes",
      };
    else if (path === "/short-studio/jobs/plan-job")
      body = {
        id: "plan-job",
        kind: "storyboard",
        status: "ready",
        phase: "Storyboard ready",
        brief: { ...brief, category },
        short_id: "short-1",
        storyboard_request: {
          brief_id: brief.id,
          storyline_id: "story-1",
          sequence_id: sequence.id,
        },
      };
    else if (path === "/content-series/episodes/short-1") body = detail();
    else if (path === "/shorts/short-1/script/approve") {
      state = { ...state, approved: true };
      body = state;
    } else if (path === "/shorts/short-1/produce") {
      state = {
        ...state,
        status: "queued",
        phase: "Rendering your selected frames",
      };
      body = state;
    } else if (path === "/shorts/short-1" && method === "GET") {
      state = {
        ...state,
        status: "review",
        phase: "Review the video",
        has_output: true,
      };
      body = state;
    } else if (path === "/shorts/short-1" && method === "DELETE") {
      deleted = true;
      return route.fulfill({ status: 204 });
    } else if (path === "/shorts") body = deleted ? [] : [state];
    else if (path.includes(".mp4"))
      return route.fulfill({ contentType: "video/mp4", body: Buffer.alloc(0) });
    else
      return route.fulfill({
        status: 404,
        json: { detail: `Unexpected request ${method} ${path}` },
      });
    await route.fulfill({ json: body });
  });
}

test("repo URL to storyline, visual sequence, storyboard and production", async ({
  page,
}, testInfo) => {
  await setup(page);
  await page.goto("/create");
  await expect(page.getByRole("button", { name: "New niche" })).toHaveCount(0);
  await page.getByLabel("Public GitHub repo URL").fill(repo);
  await page
    .getByRole("button", { name: /Find storylines with Ollama/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Which story would you watch?" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("storylines.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: /Find your photos again 1/ }).click();
  await expect(
    page.getByRole("heading", { name: "Choose your frames" }),
  ).toBeVisible();
  await expect(page.locator(".frame-picker-preview iframe")).toHaveCount(1);
  await page.getByRole("button", { name: /Choose myself/ }).click();
  await page.getByRole("button", { name: "Scene 2: Purpose" }).click();
  await page.getByLabel("Frame for scene 2").selectOption("blueprint");
  await expect(page.locator(".frame-selection-badge")).toHaveText(
    "✓ Selected · Scene 2",
  );
  await expect(page.locator(".frame-picker-preview iframe")).toHaveAttribute(
    "src",
    /blueprint/,
  );
  await page.screenshot({
    path: testInfo.outputPath("frame-picker.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Build my storyboard →" }).click();
  await expect(
    page.getByRole("heading", { name: "Your storyboard" }),
  ).toBeVisible();
  await expect(page.locator(".series-storyboard-image")).toHaveCount(6);
  await expect(page.getByLabel("Editorial suggestions")).toContainText(
    "Beat 3 repeats beat 2",
  );
  await page.screenshot({
    path: testInfo.outputPath("storyboard.png"),
    fullPage: true,
  });
  await expect(
    page.getByText(/This version uses music and on-screen text/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create music-only video" }).click();
  await expect(
    page.getByText("Rendering your selected frames", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Review the video", { exact: true })).toBeVisible(
    { timeout: 10000 },
  );
});

test("tech tricks need no repo or mandatory topic and remain usable on mobile", async ({
  page,
}) => {
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/create");
  await page.getByRole("button", { name: /Tech tricks Let Ollama/ }).click();
  await expect(page.getByLabel("Public GitHub repo URL")).toHaveCount(0);
  await page.getByRole("button", { name: /Find exciting tech tricks/ }).click();
  await expect(
    page.getByRole("heading", { name: "Which story would you watch?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Find your photos again 1/ }).click();
  await expect(
    page.getByRole("heading", { name: "Choose your frames" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("separate frame library presents sequences and individual scene previews", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/frames");
  await expect(
    page.getByRole("heading", { name: "Frame library", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".individual-frame-card")).toHaveCount(24);
  await expect(
    page.getByRole("heading", { name: "Kinetic poster" }),
  ).toBeVisible();
  await page.getByLabel("Collection").selectOption("3");
  await expect(page.locator(".individual-frame-card")).toHaveCount(12);
  await page.getByRole("button", { name: "Complete sequences" }).click();
  await expect(page.locator(".frame-sequence-card")).toHaveCount(4);
  await expect(page.locator(".frame-strip iframe")).toHaveCount(24);
});

test("completed video can choose new frames while preserving its narration", async ({
  page,
}) => {
  await setup(page, true);
  await page.goto("/create?short=short-1");
  await expect(
    page.getByRole("heading", { name: "Your video is ready" }),
  ).toBeVisible();
  await page
    .getByText("Change frames and make a new version", { exact: true })
    .click();
  await page.getByRole("button", { name: "Scene 1: Hook" }).click();
  await page.getByLabel("Frame for scene 1").selectOption("hot-take");
  const sent = page.waitForRequest(
    (r) =>
      r.url().endsWith("/short-studio/storyboards") && r.method() === "POST",
  );
  await page
    .getByRole("button", { name: "Apply frames to a new version" })
    .click();
  expect((await sent).postDataJSON()).toMatchObject({
    source_short_id: "short-1",
    frame_mode: "manual",
    frames: ["hot-take", ...sequence.frames.slice(1)],
  });
});

test("created videos can be deleted with an inline confirmation", async ({
  page,
}) => {
  await setup(page, true);
  await page.goto("/created");
  await expect(
    page.getByRole("heading", { name: "Find your photos again" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Delete video" }).click();
  await page.getByRole("button", { name: "Keep video" }).click();
  await expect(
    page.getByRole("heading", { name: "Find your photos again" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Delete video" }).click();
  await page.getByRole("button", { name: "Confirm delete" }).click();
  await expect(page.getByText(/No videos yet/)).toBeVisible();
});

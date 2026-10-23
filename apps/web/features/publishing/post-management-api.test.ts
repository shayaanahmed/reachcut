import { afterEach, describe, expect, it, vi } from "vitest";
import { projectSchema } from "../../lib/contracts";
import {
  deleteRemotePost,
  publishAndUpdateProject,
  savePublishingDestinations,
} from "./post-management-api";

const date = "2026-10-23T10:00:00Z";
function fixture(platform = "youtube") {
  return projectSchema.parse({
    id: "project",
    title: "Project",
    original_filename: "video.mp4",
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
          rationale: "Useful clip",
          hashtags: [],
          hook: null,
          caption_style: "clean",
          emphasis: [],
          effects: [],
          cta: null,
        },
        publications: [
          {
            id: "original",
            platform,
            status: "published",
            title: "Original",
            description: "Old copy",
            post_url: "https://example.com/original",
            social_account_id: "account",
            created_at: date,
            published_at: date,
            metric_snapshots: [],
          },
        ],
      },
    ],
  });
}
afterEach(() => vi.unstubAllGlobals());
describe("publishing existing posts", () => {
  it("accepts a deleted publication returned after remote deletion", async () => {
    const project = fixture("instagram");
    const response = JSON.parse(JSON.stringify(project));
    response.clips[0].publications[0].status = "deleted";
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", fetch);

    const result = await deleteRemotePost("original");

    expect(result.clips[0].publications[0].status).toBe("deleted");
    expect(projectSchema.array().parse([response])[0]).toEqual(result);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/publications/original/delete-remote"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("updates an existing identity and queues only new destinations", async () => {
    const project = fixture();
    const fetch = vi.fn().mockImplementation(
      async (path: string) =>
        new Response(
          JSON.stringify(
            path.endsWith("/management")
              ? {
                  capabilities: {
                    update: true,
                    delete: true,
                    title: true,
                    explanation: "",
                  },
                  suggested: { title: "New", description: "Copy" },
                  needs_update: true,
                  operation: null,
                  history: [],
                }
              : project,
          ),
          { status: 200 },
        ),
    );
    vi.stubGlobal("fetch", fetch);
    await savePublishingDestinations(
      project.clips[0],
      [
        {
          social_account_id: "account",
          title: "New",
          description: "Copy",
          privacy_status: "public",
        },
        {
          social_account_id: "new-account",
          title: "New",
          description: "Copy",
          privacy_status: "public",
        },
      ],
      vi.fn(),
    );
    expect(fetch.mock.calls[1][0]).toBe("/api/publications/original/remote");
    expect(fetch.mock.calls[1][1].method).toBe("PUT");
    expect(fetch.mock.calls[2][0]).toBe("/api/clips/clip/publish-batch");
    expect(JSON.parse(fetch.mock.calls[2][1].body).publications).toEqual([
      expect.objectContaining({ social_account_id: "new-account" }),
    ]);
  });
  it("reports a manual action for unsupported edits without sending a mutation", async () => {
    const project = fixture("instagram");
    const fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          capabilities: {
            update: false,
            delete: true,
            title: false,
            explanation: "Open Instagram to edit its caption.",
          },
          suggested: { title: "New", description: "Copy" },
          needs_update: true,
          operation: null,
          history: [],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    const result = await savePublishingDestinations(
      project.clips[0],
      [
        {
          social_account_id: "account",
          title: "New",
          description: "Copy",
          privacy_status: "public",
        },
      ],
      vi.fn(),
    );
    expect(result.outcomes).toMatchObject([
      { state: "manual", platform: "instagram" },
    ]);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1].method).toBe("GET");
  });
  it("updates supported destinations even when a selected Instagram post cannot be edited", async () => {
    const project = fixture();
    project.clips[0].publications.push({
      ...project.clips[0].publications[0],
      id: "instagram-post",
      platform: "instagram",
      social_account_id: "instagram-account",
    });
    const fetch = vi.fn().mockImplementation(
      async (path: string) =>
        new Response(
          JSON.stringify(
            path.endsWith("/management")
              ? {
                  capabilities: {
                    update: !path.includes("instagram-post"),
                    delete: true,
                    title: true,
                    explanation: "Open Instagram to edit.",
                  },
                  suggested: {
                    title: "Latest",
                    description: "Caption #Github",
                  },
                  needs_update: true,
                  operation: null,
                  history: [],
                }
              : project,
          ),
          { status: 200 },
        ),
    );
    vi.stubGlobal("fetch", fetch);
    const changed = vi.fn();
    const result = await savePublishingDestinations(
      project.clips[0],
      ["account", "instagram-account"].map((id) => ({
        social_account_id: id,
        title: "Latest",
        description: "Caption #Github",
        privacy_status: "public",
      })),
      changed,
    );
    expect(result.outcomes.map((outcome) => outcome.state)).toEqual([
      "updated",
      "manual",
    ]);
    expect(
      fetch.mock.calls.filter((call) => call[1]?.method === "PUT"),
    ).toHaveLength(1);
    expect(changed).toHaveBeenCalledWith(project);
    expect(
      fetch.mock.calls.some((call) => call[0].includes("publish-batch")),
    ).toBe(false);
  });
  it("bulk publishing updates an existing post with latest pipeline copy", async () => {
    const project = fixture();
    const fetch = vi.fn().mockImplementation(
      async (path: string) =>
        new Response(
          JSON.stringify(
            path.endsWith("/publish-batch")
              ? {
                  project,
                  queued: 0,
                  skipped: [
                    {
                      clip_id: "clip",
                      account_id: "account",
                      reason: "Already queued or published",
                    },
                  ],
                }
              : path.endsWith("/management")
                ? {
                    capabilities: {
                      update: true,
                      delete: true,
                      title: true,
                      explanation: "",
                    },
                    suggested: {
                      title: "Latest",
                      description: "Latest pipeline caption",
                    },
                    needs_update: true,
                    operation: null,
                    history: [],
                  }
                : project,
          ),
          { status: 200 },
        ),
    );
    vi.stubGlobal("fetch", fetch);
    const result = await publishAndUpdateProject(
      "project",
      ["clip"],
      ["account"],
      vi.fn(),
    );
    expect(result.updated).toBe(1);
    expect(result.skipped).toEqual([]);
    expect(fetch.mock.calls.at(-1)![0]).toBe(
      "/api/publications/original/remote",
    );
    expect(JSON.parse(fetch.mock.calls.at(-1)![1].body)).toEqual({
      title: "Latest",
      description: "Latest pipeline caption",
    });
  });
});

describe("destination isolation and retries", () => {
  it("continues to a second new destination when the first one fails", async () => {
    const project = fixture();
    project.clips[0].publications = [];
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Reconnect first account" }), {
          status: 409,
        }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(project)));
    vi.stubGlobal("fetch", fetch);
    const result = await savePublishingDestinations(
      project.clips[0],
      ["first", "second"].map((id) => ({
        social_account_id: id,
        title: "New",
        description: "Caption",
        privacy_status: "public",
      })),
      vi.fn(),
    );
    expect(result.outcomes.map((outcome) => outcome.state)).toEqual([
      "failed",
      "queued",
    ]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it.each([
    ["current", false, null],
    ["blocked", true, null],
    ["blocked", false, { state: "working", action: "update", error: null }],
  ] as const)(
    "reports %s without submitting an unnecessary or overlapping update",
    async (state, reconnect, operation) => {
      const project = fixture();
      const fetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            capabilities: {
              update: true,
              delete: true,
              title: true,
              explanation: "",
              reconnect_required: reconnect,
              connection_issue: "Reconnect channel",
            },
            suggested: { title: "Original", description: "Old copy" },
            needs_update: false,
            operation,
            history: [],
          }),
        ),
      );
      vi.stubGlobal("fetch", fetch);
      const result = await savePublishingDestinations(
        project.clips[0],
        [
          {
            social_account_id: "account",
            title: "Original",
            description: "Old copy",
            privacy_status: "public",
          },
        ],
        vi.fn(),
      );
      expect(result.outcomes[0].state).toBe(state);
      expect(fetch).toHaveBeenCalledTimes(1);
      expect(fetch.mock.calls[0][1].method).toBe("GET");
    },
  );
  it("does not queue a destination that already has an uncertain upload", async () => {
    const project = fixture();
    project.clips[0].publications[0].status = "uncertain";
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const result = await savePublishingDestinations(
      project.clips[0],
      [
        {
          social_account_id: "account",
          title: "New",
          description: "New",
          privacy_status: "public",
        },
      ],
      vi.fn(),
    );
    expect(result.outcomes[0].state).toBe("blocked");
    expect(fetch).not.toHaveBeenCalled();
  });
});

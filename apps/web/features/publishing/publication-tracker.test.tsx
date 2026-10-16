import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Project, SocialAccount } from "../../lib/contracts";
import { PublicationTracker } from "./publication-tracker";

const clip = {
  id: "clip-1",
  approval_status: "approved",
  preview_path: null,
  final_path: "/clips/clip-1/final.mp4",
  thumbnail_ready: false,
  publications: [],
  plan: {
    schema_version: "1.0",
    source: { start_seconds: 0, end_seconds: 30 },
    source_slices: [],
    optimization_goal: "views",
    content_mode: "auto",
    clip_type: "highlight",
    enhancement_level: "clean",
    video_template: "custom",
    scores: {
      overall: 88,
      hook: 88,
      clarity: 88,
      payoff: 88,
      visual_interest: 88,
    },
    rationale: "A complete idea.",
    suggested_title: "A useful idea",
    hashtags: ["#Clip"],
    hook: null,
    caption_style: "clean",
    caption_config: {
      preset: "custom",
      enabled: true,
      position: "bottom",
      font_family: "Noto Sans",
      font_size: 58,
      text_color: "#FFFFFF",
      highlight_color: "#D8FF42",
      outline_color: "#111111",
      animation: "pop",
      highlighted_words: [],
      max_words_per_line: 5,
      text_override: null,
      source_language: null,
      target_language: null,
      translation_mode: "original",
      translated_text: null,
    },
    frame_style: "blurred_background",
    crop_focus_x: 0.5,
    crop_focus_y: 0.5,
    tracking: { enabled: false, strategy: "static", keyframes: [] },
    transition_style: "cut",
    transition_duration_seconds: 0.2,
    secondary_media: [],
    audio_track_index: 0,
    thumbnail: {
      template: "speaker",
      headline: null,
      frame_time_seconds: null,
      generated: false,
    },
    emphasis: [],
    effects: [],
    cta: null,
  },
  publish_recommendation: {
    score: 88,
    confidence: "high",
    reasons: ["Strong hook", "Short-form duration"],
  },
} as Project["clips"][number];

const account = {
  id: "account-1",
  platform: "youtube",
  label: "Main YouTube",
  username: "creator",
  profile_url: "https://youtube.com/@creator",
  default_hashtags: ["#CreatorTips"],
  default_cta: "Follow for more",
  default_campaign_url: "https://example.com/newsletter",
  currency: "EUR",
  connection_status: "connected",
  is_default: true,
  is_active: true,
  created_at: "2026-10-02T10:00:00Z",
  updated_at: "2026-10-02T10:00:00Z",
} satisfies SocialAccount;

describe("publication tracker", () => {
  it("selects the default destination when accounts finish loading", () => {
    const props = {
      clip,
      isPending: () => false,
      onPublish: vi.fn(),
      onRecordMetrics: vi.fn(),
      onRefreshPublication: vi.fn(),
      onSyncMetrics: vi.fn(),
      onDeletePublication: vi.fn(),
    };
    const view = render(<PublicationTracker {...props} accounts={[]} />);

    view.rerender(<PublicationTracker {...props} accounts={[account]} />);

    expect(
      view
        .getByRole("button", { name: /Main YouTube/ })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    view.unmount();
  });

  it("prefills publishing metadata from the configured default account", () => {
    const view = render(
      <PublicationTracker
        clip={clip}
        accounts={[account]}
        isPending={() => false}
        onPublish={vi.fn()}
        onRecordMetrics={vi.fn()}
        onRefreshPublication={vi.fn()}
        onSyncMetrics={vi.fn()}
        onDeletePublication={vi.fn()}
      />,
    );

    expect(
      view
        .getByRole("button", { name: /Main YouTube/ })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      (screen.getByLabelText("Suggested title") as HTMLInputElement).value,
    ).toBe("A useful idea");
    expect(
      (screen.getByLabelText("Description and hashtags") as HTMLTextAreaElement)
        .value,
    ).toBe(
      "A useful idea\n\n#Clip #CreatorTips\n\nFollow for more\n\nhttps://example.com/newsletter",
    );
    expect(
      (
        view.getByRole("button", {
          name: /Publish to YouTube Shorts/,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
    expect(screen.queryByLabelText("Published post URL")).toBeNull();
  });

  it("enables automatic publishing for a connected non-YouTube account", () => {
    const view = render(
      <PublicationTracker
        clip={clip}
        accounts={[
          {
            ...account,
            id: "tiktok-1",
            platform: "tiktok",
            label: "Main TikTok",
          },
        ]}
        isPending={() => false}
        onPublish={vi.fn()}
        onRecordMetrics={vi.fn()}
        onRefreshPublication={vi.fn()}
        onSyncMetrics={vi.fn()}
        onDeletePublication={vi.fn()}
      />,
    );

    expect(
      (
        view.container.querySelector(
          "button.publish-primary-action",
        ) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
    expect(
      view.container.querySelector('option[value="friends"]'),
    ).toBeTruthy();
  });

  it("queues the same clip for multiple selected destinations", () => {
    const publish = vi.fn().mockResolvedValue(undefined);
    const instagram = {
      ...account,
      id: "instagram-1",
      platform: "instagram" as const,
      label: "Main Instagram",
      username: "creator.ig",
      is_default: false,
    };
    const view = render(
      <PublicationTracker
        clip={clip}
        accounts={[account, instagram]}
        isPending={() => false}
        onPublish={publish}
        onRecordMetrics={vi.fn()}
        onRefreshPublication={vi.fn()}
        onSyncMetrics={vi.fn()}
        onDeletePublication={vi.fn()}
      />,
    );

    fireEvent.click(
      view.getByRole("button", { name: /Add Main Instagram to/ }),
    );
    fireEvent.click(
      view.getByRole("button", { name: "Publish to 2 destinations" }),
    );

    expect(publish).toHaveBeenCalledWith(
      "clip-1",
      expect.arrayContaining([
        expect.objectContaining({ social_account_id: "account-1" }),
        expect.objectContaining({ social_account_id: "instagram-1" }),
      ]),
    );
  });

  it.each(["youtube", "instagram", "facebook"] as const)(
    "offers an immediate metrics sync for a published %s clip",
    (platform) => {
      const syncMetrics = vi.fn().mockResolvedValue(undefined);
      const view = render(
        <PublicationTracker
          clip={{
            ...clip,
            publications: [
              {
                id: "publication-1",
                platform,
                status: "published",
                post_url: "https://www.youtube.com/shorts/video-123",
                title: "Published clip",
                description: "",
                published_at: "2026-10-02T10:00:00Z",
                created_at: "2026-10-02T10:00:00Z",
                social_account_id: "account-1",
                account_label: "Main YouTube",
                account_username: "creator",
                provider_publication_id: null,
                metric_snapshots: [],
              },
            ],
          }}
          accounts={[account]}
          isPending={() => false}
          onPublish={vi.fn()}
          onRecordMetrics={vi.fn()}
          onRefreshPublication={vi.fn()}
          onSyncMetrics={syncMetrics}
          onDeletePublication={vi.fn()}
        />,
      );

      fireEvent.click(
        within(view.container).getByRole("button", { name: "Sync views" }),
      );

      expect(syncMetrics).toHaveBeenCalledWith("publication-1");
    },
  );

  it("does not present a YouTube upload as playable while it is processing", () => {
    const view = render(
      <PublicationTracker
        clip={{
          ...clip,
          publications: [
            {
              id: "publication-1",
              platform: "youtube",
              status: "processing",
              post_url: "https://www.youtube.com/watch?v=video-123",
              title: "Processing clip",
              description: "",
              published_at: null,
              created_at: "2026-10-03T10:00:00Z",
              social_account_id: "account-1",
              account_label: "Main YouTube",
              account_username: "creator",
              provider_publication_id: "video-123",
              metric_snapshots: [],
            },
          ],
        }}
        accounts={[account]}
        isPending={() => false}
        onPublish={vi.fn()}
        onRecordMetrics={vi.fn()}
        onRefreshPublication={vi.fn()}
        onSyncMetrics={vi.fn()}
        onDeletePublication={vi.fn()}
      />,
    );

    expect(view.getByText("Refresh status")).toBeTruthy();
    expect(
      view.container.querySelector(
        'a[href="https://www.youtube.com/watch?v=video-123"]',
      ),
    ).toBeNull();
  });

  it("keeps unrelated publication actions available while metrics sync", () => {
    const publication = {
      id: "publication-1",
      platform: "youtube" as const,
      status: "published" as const,
      post_url: "https://www.youtube.com/shorts/video-123",
      title: "Published clip",
      description: "",
      published_at: "2026-10-02T10:00:00Z",
      created_at: "2026-10-02T10:00:00Z",
      social_account_id: "account-1",
      account_label: "Main YouTube",
      account_username: "creator",
      provider_publication_id: "video-123",
      metric_snapshots: [],
    };
    const view = render(
      <PublicationTracker
        clip={{ ...clip, publications: [publication] }}
        accounts={[account]}
        isPending={(key) => key === "publication:publication-1:sync"}
        onPublish={vi.fn()}
        onRecordMetrics={vi.fn()}
        onRefreshPublication={vi.fn()}
        onSyncMetrics={vi.fn()}
        onDeletePublication={vi.fn()}
      />,
    );
    const tracker = within(view.container);

    expect(
      (tracker.getByRole("button", { name: "Syncing…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      (
        tracker.getByRole("button", {
          name: "Check status",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
  });
});

it("shows the saved provider failure and publication attempt ID", () => {
  const view = render(
    <PublicationTracker
      clip={{
        ...clip,
        publications: [
          {
            id: "failed-attempt-1",
            platform: "instagram",
            status: "failed",
            post_url: null,
            title: "A useful idea",
            description: "#Clip",
            published_at: null,
            created_at: "2026-10-16T10:00:00Z",
            social_account_id: "account-1",
            account_label: "Instagram",
            account_username: "creator",
            provider_publication_id: null,
            metric_snapshots: [],
            error:
              "Instagram video upload failed; Meta 1363008: FILE_NOT_FOUND; bytes transferred: 0",
          },
        ],
      }}
      accounts={[account]}
      isPending={() => false}
      onPublish={vi.fn()}
      onRecordMetrics={vi.fn()}
      onRefreshPublication={vi.fn()}
      onSyncMetrics={vi.fn()}
      onDeletePublication={vi.fn()}
    />,
  );
  const alert = view.getByRole("alert");
  expect(alert.textContent).toContain("1363008: FILE_NOT_FOUND");
  expect(alert.textContent).toContain("Attempt: failed-attempt-1");
  expect(alert.textContent).not.toContain(
    "Check the account connection and try publishing again",
  );
  view.unmount();
});

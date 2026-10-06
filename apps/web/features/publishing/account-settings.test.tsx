import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountSettings } from "./account-settings";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    listSocialAccounts: vi.fn(),
    publishingCapabilities: vi.fn(),
    socialAccountReadiness: vi.fn(),
  };
});

describe("account settings", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.mocked(api.listSocialAccounts).mockResolvedValue([
      {
        id: "youtube-1",
        platform: "youtube",
        label: "Main YouTube",
        username: "creator",
        profile_url: null,
        default_hashtags: [],
        default_cta: "",
        default_campaign_url: null,
        currency: "EUR",
        connection_status: "connected",
        is_default: true,
        is_active: true,
        created_at: "2026-10-02T10:00:00Z",
        updated_at: "2026-10-02T10:00:00Z",
      },
    ]);
    vi.mocked(api.publishingCapabilities).mockResolvedValue({
      youtube_configured: true,
      automatic_platforms: ["youtube"],
      configured_platforms: ["youtube"],
    });
    vi.mocked(api.socialAccountReadiness).mockResolvedValue([
      {
        account_id: "youtube-1",
        platform: "youtube",
        provider_configured: true,
        credentials_available: true,
        publishing_ready: true,
        issues: [],
      },
    ]);
  });

  it("lets an existing YouTube connection request newly added permissions", async () => {
    render(<AccountSettings />);

    const reconnect = await screen.findByRole("link", {
      name: "Reconnect",
    });

    expect(reconnect.getAttribute("href")).toContain(
      "/social-accounts/youtube-1/connect",
    );
    expect(screen.getByText("● Ready to publish")).toBeTruthy();
    expect(screen.getByText("Secure credentials")).toBeTruthy();
  });

  it("surfaces a backend-verified account that needs reconnection", async () => {
    vi.mocked(api.socialAccountReadiness).mockResolvedValue([
      {
        account_id: "youtube-1",
        platform: "youtube",
        provider_configured: true,
        credentials_available: false,
        publishing_ready: false,
        issues: ["credentials_missing"],
      },
    ]);

    render(<AccountSettings />);

    expect(await screen.findByText("○ Action required")).toBeTruthy();
    expect(screen.getByText("Secure credentials").className).toBe(
      "needs-action",
    );
  });
});

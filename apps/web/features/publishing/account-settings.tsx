"use client";

import { useEffect, useState } from "react";

import type { SocialAccount, SocialPlatform } from "../../lib/contracts";
import {
  archiveSocialAccount,
  createSocialAccount,
  disconnectSocialAccount,
  listSocialAccounts,
  publishingCapabilities,
  socialConnectUrl,
  updateSocialAccount,
  type PublishingCapabilities,
  type SocialAccountUpdate,
} from "./api";

const platformDetails: Record<
  SocialPlatform,
  { label: string; short: string; mark: string }
> = {
  youtube: { label: "YouTube Shorts", short: "YouTube", mark: "▶" },
  tiktok: { label: "TikTok", short: "TikTok", mark: "♪" },
  instagram: { label: "Instagram Reels", short: "Instagram", mark: "◎" },
  facebook: { label: "Facebook Reels", short: "Facebook", mark: "f" },
  x: { label: "X", short: "X", mark: "X" },
};

const platforms = Object.keys(platformDetails) as SocialPlatform[];

function accountData(data: FormData): SocialAccountUpdate {
  return {
    label: String(data.get("label")),
    username: String(data.get("username")),
    profile_url: String(data.get("profile_url") || "") || null,
    default_hashtags: String(data.get("default_hashtags") || "")
      .split(/[\s,]+/)
      .map((tag) => tag.trim())
      .filter(Boolean),
    default_cta: String(data.get("default_cta") || ""),
    default_campaign_url:
      String(data.get("default_campaign_url") || "") || null,
    currency: String(data.get("currency") || "EUR").toUpperCase(),
    is_default: data.get("is_default") === "true",
  };
}

export function AccountSettings() {
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<PublishingCapabilities>({
    youtube_configured: false,
    automatic_platforms: [],
    configured_platforms: [],
  });

  async function refresh() {
    setAccounts(await listSocialAccounts());
  }

  useEffect(() => {
    void Promise.all([listSocialAccounts(), publishingCapabilities()])
      .then(([items, available]) => {
        setAccounts(items);
        setCapabilities(available);
      })
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, []);

  async function mutate(operation: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await operation();
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Account update failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function addAndConnect(platform: SocialPlatform) {
    setBusy(true);
    setError(null);
    try {
      const created = await createSocialAccount({
        platform,
        label: platformDetails[platform].label,
        username: "",
        profile_url: null,
        default_hashtags: [],
        default_cta: "",
        default_campaign_url: null,
        currency: "EUR",
        is_default: !accounts.some((account) => account.platform === platform),
      });
      window.location.assign(socialConnectUrl(created.id));
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not add account",
      );
      setBusy(false);
    }
  }

  return (
    <main className="page accounts-page">
      <div className="topbar">
        <div>
          <span className="eyebrow">SETTINGS</span>
          <h1>Connected accounts</h1>
          <p>
            Choose a platform, approve access there, and come straight back to
            Clipper. No tokens to copy or account IDs to hunt down.
          </p>
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <section className="connect-panel" aria-labelledby="connect-heading">
        <div className="connect-panel-heading">
          <div>
            <span className="eyebrow">ADD A DESTINATION</span>
            <h2 id="connect-heading">Where do you publish?</h2>
          </div>
          <small>
            OAuth credentials stay encrypted in your private data folder.
          </small>
        </div>
        <div className="platform-picker">
          {platforms.map((platform) => {
            const detail = platformDetails[platform];
            const configured =
              capabilities.configured_platforms.includes(platform);
            return (
              <button
                key={platform}
                type="button"
                className={`platform-choice ${platform}`}
                disabled={busy || !configured}
                title={
                  configured
                    ? `Connect ${detail.short}`
                    : `${detail.short} OAuth has not been configured by the workspace owner`
                }
                onClick={() => void addAndConnect(platform)}
              >
                <span aria-hidden="true">{detail.mark}</span>
                <strong>{detail.short}</strong>
                <small>{configured ? "Connect →" : "Setup required"}</small>
              </button>
            );
          })}
        </div>
      </section>
      <section className="section-block" aria-labelledby="configured-accounts">
        <div className="section-heading">
          <div>
            <span className="eyebrow">PUBLISHING DESTINATIONS</span>
            <h2 id="configured-accounts">Your accounts</h2>
          </div>
          <span>{accounts.length} added</span>
        </div>
        {loading ? (
          <div className="loading-card">Loading accounts…</div>
        ) : accounts.length === 0 ? (
          <div className="empty-state compact">
            <h3>No accounts yet</h3>
            <p>Select a platform above to connect your first destination.</p>
          </div>
        ) : (
          <div className="account-list">
            {accounts.map((account) => {
              const connected = account.connection_status === "connected";
              const configured = capabilities.configured_platforms.includes(
                account.platform,
              );
              return (
                <article className="account-card" key={account.id}>
                  <div className="account-card-heading">
                    <span className={`account-avatar ${account.platform}`}>
                      {platformDetails[account.platform].mark}
                    </span>
                    <span
                      className={`connection-badge ${connected ? "connected" : ""}`}
                    >
                      {connected ? "● Connected" : "○ Not connected"}
                    </span>
                  </div>
                  <span className={`account-platform ${account.platform}`}>
                    {platformDetails[account.platform].label}
                  </span>
                  <h3>{account.label}</h3>
                  <p>
                    {account.username
                      ? `@${account.username}`
                      : "Profile details sync after connection"}
                  </p>
                  <div className="account-card-actions">
                    {configured && (
                      <a href={socialConnectUrl(account.id)}>
                        {connected ? "Reconnect" : "Connect"}
                      </a>
                    )}
                    {connected && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          void mutate(() => disconnectSocialAccount(account.id))
                        }
                      >
                        Disconnect
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Remove “${account.label}”? Existing publication history will remain.`,
                          )
                        )
                          void mutate(() => archiveSocialAccount(account.id));
                      }}
                    >
                      Remove
                    </button>
                  </div>
                  {!configured && (
                    <small className="setup-hint">
                      Ask the workspace owner to configure{" "}
                      {platformDetails[account.platform].short} OAuth.
                    </small>
                  )}
                  <details className="account-edit">
                    <summary>Edit publishing defaults</summary>
                    <AccountForm
                      account={account}
                      busy={busy}
                      onSave={(data) =>
                        mutate(() =>
                          updateSocialAccount(account.id, accountData(data)),
                        )
                      }
                    />
                  </details>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}

function AccountForm({
  account,
  busy,
  onSave,
}: {
  account: SocialAccount;
  busy: boolean;
  onSave: (data: FormData) => Promise<void>;
}) {
  return (
    <form className="account-form compact" action={onSave}>
      <label>
        Account label
        <input
          name="label"
          defaultValue={account.label}
          maxLength={100}
          required
        />
      </label>
      <label>
        Username or channel
        <input
          name="username"
          defaultValue={account.username}
          maxLength={100}
        />
      </label>
      <label>
        Profile URL
        <input
          name="profile_url"
          type="url"
          pattern="https://.*"
          defaultValue={account.profile_url ?? ""}
        />
      </label>
      <label>
        Default hashtags
        <input
          name="default_hashtags"
          defaultValue={account.default_hashtags.join(" ")}
          placeholder="#clips #creator"
        />
      </label>
      <label>
        Default CTA
        <input
          name="default_cta"
          defaultValue={account.default_cta}
          maxLength={500}
        />
      </label>
      <label>
        Campaign URL
        <input
          name="default_campaign_url"
          type="url"
          pattern="https://.*"
          defaultValue={account.default_campaign_url ?? ""}
        />
      </label>
      <label>
        Reporting currency
        <input
          name="currency"
          defaultValue={account.currency}
          minLength={3}
          maxLength={3}
          required
        />
      </label>
      <label className="check account-default-check">
        <input
          name="is_default"
          type="checkbox"
          value="true"
          defaultChecked={account.is_default}
        />
        <span>Use as the default for this platform</span>
      </label>
      <button className="primary-button" disabled={busy}>
        Save defaults
      </button>
    </form>
  );
}

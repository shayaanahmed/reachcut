"use client";

import { useEffect, useState } from "react";

import type {
  AccountConnectionReadiness,
  SocialAccount,
  SocialPlatform,
} from "../../lib/contracts";
import {
  archiveSocialAccount,
  createSocialAccount,
  disconnectSocialAccount,
  listSocialAccounts,
  publishingCapabilities,
  socialAccountReadiness,
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
  const [readiness, setReadiness] = useState<AccountConnectionReadiness[]>([]);
  const [loading, setLoading] = useState(true);
  const [operations, setOperations] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<PublishingCapabilities>({
    youtube_configured: false,
    automatic_platforms: [],
    configured_platforms: [],
  });

  async function refresh() {
    const [items, states] = await Promise.all([
      listSocialAccounts(),
      socialAccountReadiness(),
    ]);
    setAccounts(items);
    setReadiness(states);
  }

  useEffect(() => {
    void Promise.all([
      listSocialAccounts(),
      publishingCapabilities(),
      socialAccountReadiness(),
    ])
      .then(([items, available, states]) => {
        setAccounts(items);
        setCapabilities(available);
        setReadiness(states);
      })
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, []);

  function isPending(key: string) {
    return Boolean(operations[key]);
  }

  async function mutate(key: string, operation: () => Promise<unknown>) {
    setOperations((current) => ({ ...current, [key]: true }));
    setError(null);
    try {
      await operation();
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Account update failed",
      );
    } finally {
      setOperations((current) => ({ ...current, [key]: false }));
    }
  }

  async function addAndConnect(platform: SocialPlatform) {
    const operationKey = `platform:${platform}:connect`;
    setOperations((current) => ({ ...current, [operationKey]: true }));
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
      setOperations((current) => ({ ...current, [operationKey]: false }));
    }
  }

  const readyCount = readiness.filter((state) => state.publishing_ready).length;
  const configuredCount = capabilities.configured_platforms.length;
  const defaultsCount = accounts.filter(
    (account) => account.default_cta || account.default_hashtags.length > 0,
  ).length;
  const readinessById = new Map(
    readiness.map((state) => [state.account_id, state]),
  );

  return (
    <main className="page accounts-page">
      <div className="topbar accounts-topbar">
        <div>
          <span className="eyebrow">DISTRIBUTION SETTINGS</span>
          <h1>Publishing accounts</h1>
          <p>
            Connect destinations once, verify their publishing health, and set
            reusable campaign defaults for every export.
          </p>
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <section className="account-health-grid" aria-label="Account health">
        <article>
          <span>Ready to publish</span>
          <strong>{readyCount}</strong>
          <small>Backend-verified connections</small>
        </article>
        <article>
          <span>Accounts added</span>
          <strong>{accounts.length}</strong>
          <small>Active destinations</small>
        </article>
        <article>
          <span>Providers enabled</span>
          <strong>
            {configuredCount}/{platforms.length}
          </strong>
          <small>OAuth configuration</small>
        </article>
        <article>
          <span>Defaults prepared</span>
          <strong>
            {defaultsCount}/{accounts.length || 0}
          </strong>
          <small>CTA or hashtag presets</small>
        </article>
      </section>
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
            const pending = isPending(`platform:${platform}:connect`);
            const accountCount = accounts.filter(
              (account) => account.platform === platform,
            ).length;
            return (
              <button
                key={platform}
                type="button"
                className={`platform-choice ${platform}`}
                disabled={pending || !configured}
                title={
                  configured
                    ? `Connect ${detail.short}`
                    : `${detail.short} OAuth has not been configured by the workspace owner`
                }
                onClick={() => void addAndConnect(platform)}
              >
                <span aria-hidden="true">{detail.mark}</span>
                <strong>{detail.short}</strong>
                <small>
                  {pending
                    ? "Opening…"
                    : !configured
                      ? "Provider setup required"
                      : accountCount > 0
                        ? `Add another · ${accountCount} active`
                        : "Connect account →"}
                </small>
              </button>
            );
          })}
        </div>
      </section>
      <section className="section-block" aria-labelledby="configured-accounts">
        <div className="section-heading">
          <div>
            <span className="eyebrow">ACCOUNT OPERATIONS</span>
            <h2 id="configured-accounts">Destinations and readiness</h2>
          </div>
          <span>{readyCount} ready now</span>
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
              const state = readinessById.get(account.id);
              const connected = state?.credentials_available ?? false;
              const ready = state?.publishing_ready ?? false;
              const configured = capabilities.configured_platforms.includes(
                account.platform,
              );
              const disconnectKey = `account:${account.id}:disconnect`;
              const archiveKey = `account:${account.id}:archive`;
              const updateKey = `account:${account.id}:update`;
              return (
                <article className="account-card" key={account.id}>
                  <div className="account-card-heading">
                    <span className={`account-avatar ${account.platform}`}>
                      {platformDetails[account.platform].mark}
                    </span>
                    <span
                      className={`connection-badge ${ready ? "connected" : ""}`}
                    >
                      {ready ? "● Ready to publish" : "○ Action required"}
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
                  <div
                    className="account-readiness"
                    aria-label="Readiness checks"
                  >
                    <ReadinessCheck
                      ready={state?.provider_configured ?? configured}
                      label="Provider configured"
                    />
                    <ReadinessCheck
                      ready={connected}
                      label="Secure credentials"
                    />
                    <ReadinessCheck
                      ready={
                        Boolean(account.default_cta) ||
                        account.default_hashtags.length > 0
                      }
                      label="Publishing defaults"
                      optional
                    />
                  </div>
                  <div className="account-card-actions">
                    {configured && (
                      <a href={socialConnectUrl(account.id)}>
                        {connected ? "Reconnect" : "Connect"}
                      </a>
                    )}
                    {connected && (
                      <button
                        type="button"
                        disabled={isPending(disconnectKey)}
                        onClick={() =>
                          void mutate(disconnectKey, () =>
                            disconnectSocialAccount(account.id),
                          )
                        }
                      >
                        {isPending(disconnectKey)
                          ? "Disconnecting…"
                          : "Disconnect"}
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={isPending(archiveKey)}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Remove “${account.label}”? Existing publication history will remain.`,
                          )
                        )
                          void mutate(archiveKey, () =>
                            archiveSocialAccount(account.id),
                          );
                      }}
                    >
                      {isPending(archiveKey) ? "Removing…" : "Remove"}
                    </button>
                  </div>
                  {!configured && (
                    <small className="setup-hint">
                      Ask the workspace owner to configure{" "}
                      {platformDetails[account.platform].short} OAuth.
                    </small>
                  )}
                  <details className="account-edit">
                    <summary>Publishing defaults and profile</summary>
                    <AccountForm
                      account={account}
                      busy={isPending(updateKey)}
                      onSave={(data) =>
                        mutate(updateKey, () =>
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

function ReadinessCheck({
  ready,
  label,
  optional = false,
}: {
  ready: boolean;
  label: string;
  optional?: boolean;
}) {
  return (
    <span className={ready ? "ready" : "needs-action"}>
      <b aria-hidden="true">{ready ? "✓" : optional ? "○" : "!"}</b>
      {label}
      {optional && !ready ? " (recommended)" : ""}
    </span>
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

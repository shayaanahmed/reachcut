"use client";

import { GroupManager } from "./group-manager";
import { AccountConnectionPicker } from "./account-connection-picker";
import { useEffect, useState } from "react";

import type {
  AccountConnectionReadiness,
  SocialAccount,
  SocialPlatform,
} from "../../lib/contracts";
import {
  archiveSocialAccount,
  disconnectSocialAccount,
  listSocialAccounts,
  publishingCapabilities,
  socialAccountReadiness,
  socialConnectUrl,
  socialPlatformConnectUrl,
  updateSocialAccount,
  type ProviderSetup,
  type PublishingCapabilities,
  type SocialAccountUpdate,
} from "./api";

const platformDetails: Record<
  SocialPlatform,
  { label: string; short: string; mark: string; description: string }
> = {
  youtube: {
    label: "YouTube Shorts",
    short: "YouTube",
    mark: "▶",
    description: "Connect a channel with Google OAuth",
  },
  tiktok: {
    label: "TikTok",
    short: "TikTok",
    mark: "♪",
    description: "Direct Post through TikTok Login Kit",
  },
  instagram: {
    label: "Instagram Reels",
    short: "Instagram",
    mark: "◎",
    description: "Local upload through a Page-linked professional account",
  },
  facebook: {
    label: "Facebook Reels",
    short: "Facebook",
    mark: "f",
    description: "Publish to a Facebook Page",
  },
  x: {
    label: "X",
    short: "X",
    mark: "X",
    description: "OAuth 2.0 with read and write access",
  },
};

const platforms = Object.keys(platformDetails) as SocialPlatform[];

const providerGuides: Record<
  SocialPlatform,
  { app: string; products: string; scopes: string }
> = {
  youtube: {
    app: "Create a Google Cloud project and an OAuth client of type Web application.",
    products:
      "Enable YouTube Data API v3 and configure the Google Auth consent screen.",
    scopes: "youtube.upload and youtube.readonly",
  },
  tiktok: {
    app: "Create a TikTok for Developers app configured for Desktop Login Kit.",
    products:
      "Add Desktop Login Kit and Content Posting API, then enable Direct Post; ReachCut uses PKCE with a loopback callback.",
    scopes: "user.info.basic, video.publish, and video.upload",
  },
  instagram: {
    app: "Create a Meta Business app for the Facebook account that manages the linked Page.",
    products:
      "Add Facebook Login for Business and Instagram API with Facebook Login, then create a User access token configuration and copy its Configuration ID.",
    scopes:
      "pages_show_list, pages_read_engagement, business_management, instagram_basic, and instagram_content_publish",
  },
  facebook: {
    app: "Create a dedicated Meta app whose login can access the destination Page.",
    products:
      "Add Facebook Login for Business, create a User access token configuration, and keep the app in Development while testing with an app role.",
    scopes:
      "pages_show_list, pages_read_engagement, pages_manage_posts, and business_management",
  },
  x: {
    app: "Create an X Project and App, then enable OAuth 2.0 as a confidential Web App.",
    products:
      "Set read and write permissions and add the required website URL.",
    scopes:
      "tweet.read, tweet.write, users.read, media.write, and offline.access",
  },
};

function accountData(data: FormData): SocialAccountUpdate {
  return {
    label: String(data.get("label")),
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
  const [accountQuery, setAccountQuery] = useState("");
  const [accountPlatform, setAccountPlatform] = useState("");
  const [loading, setLoading] = useState(true);
  const [operations, setOperations] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedSetup, setSelectedSetup] = useState<SocialPlatform | null>(
    null,
  );
  const [capabilities, setCapabilities] = useState<PublishingCapabilities>({
    configured_platforms: [],
    provider_setup: [],
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
    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected") as SocialPlatform | null;
    const connectionError = params.get("connection_error");
    void Promise.all([
      listSocialAccounts(),
      publishingCapabilities(),
      socialAccountReadiness(),
    ])
      .then(([items, available, states]) => {
        if (connected && platformDetails[connected]) {
          setNotice(
            `${platformDetails[connected].short} is connected and ready to review.`,
          );
        }
        if (connectionError) setError(connectionError);
        setAccounts(items);
        setCapabilities({
          ...available,
          provider_setup: available.provider_setup ?? [],
        });
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

  function addAndConnect(platform: SocialPlatform) {
    const operationKey = `platform:${platform}:connect`;
    setOperations((current) => ({ ...current, [operationKey]: true }));
    setError(null);
    window.location.assign(socialPlatformConnectUrl(platform));
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
      {notice && (
        <p role="status" className="connection-notice">
          <b aria-hidden="true">✓</b>
          {notice}
        </p>
      )}
      <AccountConnectionPicker
        onConnected={async (account) => {
          setNotice(`${account.username || account.label} is connected.`);
          setError(null);
          await refresh();
        }}
      />
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
            ReachCut creates the account only after the provider confirms its
            identity. Access tokens stay encrypted locally.
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
                disabled={pending}
                title={
                  configured
                    ? `Connect ${detail.short}`
                    : `Set up ${detail.short} developer credentials`
                }
                onClick={() => {
                  if (configured) addAndConnect(platform);
                  else setSelectedSetup(platform);
                }}
              >
                <span className="platform-choice-heading">
                  <i aria-hidden="true">{detail.mark}</i>
                  <em className={configured ? "configured" : ""}>
                    {configured ? "Ready" : "Setup required"}
                  </em>
                </span>
                <strong>{detail.short}</strong>
                <p>{detail.description}</p>
                <small>
                  {pending
                    ? "Opening…"
                    : !configured
                      ? "View credential guide →"
                      : accountCount > 0
                        ? `Add another · ${accountCount} active`
                        : "Connect account →"}
                </small>
              </button>
            );
          })}
        </div>
        {selectedSetup && (
          <ProviderSetupGuide
            platform={selectedSetup}
            setup={capabilities.provider_setup.find(
              (item) => item.platform === selectedSetup,
            )}
            onClose={() => setSelectedSetup(null)}
          />
        )}
      </section>
      <GroupManager accounts={accounts} />
      <section className="section-block" aria-labelledby="configured-accounts">
        <div className="section-heading">
          <div>
            <span className="eyebrow">ACCOUNT OPERATIONS</span>
            <h2 id="configured-accounts">Destinations and readiness</h2>
          </div>
          <span>{readyCount} ready now</span>
        </div>
        <div className="publishing-project-picker">
          <label>
            Find accounts
            <input
              value={accountQuery}
              onChange={(e) => setAccountQuery(e.target.value)}
              placeholder="Search name or username"
            />
          </label>
          <label>
            Filter platform
            <select
              value={accountPlatform}
              onChange={(e) => setAccountPlatform(e.target.value)}
            >
              <option value="">All platforms</option>
              {platforms.map((p) => (
                <option value={p} key={p}>
                  {platformDetails[p].short}
                </option>
              ))}
            </select>
          </label>
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
            {accounts
              .filter(
                (a) =>
                  (!accountPlatform || a.platform === accountPlatform) &&
                  `${a.label} ${a.username}`
                    .toLowerCase()
                    .includes(accountQuery.toLowerCase()),
              )
              .map((account) => {
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
                    {account.external_account_id && (
                      <small className="account-provider-id">
                        Account ID: {account.external_account_id}
                      </small>
                    )}
                    {account.parent_page_name && (
                      <p>Facebook Page: {account.parent_page_name}</p>
                    )}
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
                      <summary>Publishing defaults</summary>
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

function ProviderSetupGuide({
  platform,
  setup,
  onClose,
}: {
  platform: SocialPlatform;
  setup?: ProviderSetup;
  onClose: () => void;
}) {
  const detail = platformDetails[platform];
  const guide = providerGuides[platform];
  const envLines = setup?.credential_fields.map((field) =>
    field.endsWith("_REDIRECT_URI")
      ? `${field}=${setup.redirect_uri}`
      : `${field}=<copy from developer portal>`,
  );

  return (
    <aside className="provider-setup-guide" aria-live="polite">
      <div className="provider-setup-heading">
        <div>
          <span className="eyebrow">DEVELOPER APP SETUP</span>
          <h3>Set up {detail.short} from scratch</h3>
        </div>
        <button type="button" onClick={onClose} aria-label="Close setup guide">
          ×
        </button>
      </div>
      <ol>
        <li>
          <strong>Create the provider app.</strong>
          <span>{guide.app}</span>
        </li>
        <li>
          <strong>Enable publishing.</strong>
          <span>{guide.products}</span>
        </li>
        <li>
          <strong>Request the minimum scopes.</strong>
          <span>{guide.scopes}.</span>
        </li>
        <li>
          <strong>Register this exact callback.</strong>
          <code>
            {setup?.redirect_uri || "Set the local callback URL in .env first"}
          </code>
        </li>
        <li>
          <strong>
            Copy the generated credentials into your private .env file.
          </strong>
          {envLines?.length ? (
            <pre>{envLines.join("\n")}</pre>
          ) : (
            <span>Restart the API to load provider setup details.</span>
          )}
        </li>
      </ol>
      <div className="provider-setup-actions">
        {setup?.developer_portal_url && (
          <a href={setup.developer_portal_url} target="_blank" rel="noreferrer">
            Open {detail.short} developer portal ↗
          </a>
        )}
        <span>Restart ReachCut after editing .env, then connect here.</span>
      </div>
    </aside>
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

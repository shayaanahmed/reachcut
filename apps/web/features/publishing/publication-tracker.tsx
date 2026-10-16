"use client";

import Link from "next/link";
import { useState } from "react";

import type {
  Project,
  SocialAccount,
  SocialAccountGroup,
} from "../../lib/contracts";
import type { MetricCreate, Platform, PublicationCreate } from "./api";

type Clip = Project["clips"][number];
type Publication = Clip["publications"][number];
type IsPending = (key: string) => boolean;

const platformDetails: Record<
  Platform,
  { label: string; shortLabel: string; glyph: string }
> = {
  youtube: { label: "YouTube Shorts", shortLabel: "YouTube", glyph: "YT" },
  tiktok: { label: "TikTok", shortLabel: "TikTok", glyph: "TT" },
  instagram: {
    label: "Instagram Reels",
    shortLabel: "Instagram",
    glyph: "IG",
  },
  facebook: {
    label: "Facebook Reels",
    shortLabel: "Facebook",
    glyph: "f",
  },
  x: { label: "X", shortLabel: "X", glyph: "X" },
};

const platformOrder: Platform[] = [
  "youtube",
  "tiktok",
  "instagram",
  "facebook",
  "x",
];

function suggestedMetadata(clip: Clip, account: SocialAccount) {
  const title =
    clip.plan.suggested_title ?? clip.plan.hook?.text ?? "New short clip";
  const hashtags = [
    ...new Set([...clip.plan.hashtags, ...account.default_hashtags]),
  ].join(" ");
  const additions = [
    hashtags,
    account.default_cta,
    account.default_campaign_url,
  ].filter(Boolean);
  const description = [title, ...additions].join("\n\n");
  if (account.platform === "x")
    return { title, description: description.slice(0, 280) };
  if (account.platform === "youtube")
    return { title: title.slice(0, 100), description };
  return { title, description };
}

function metricValue(data: FormData, name: string): number {
  return Number(data.get(name)) || 0;
}

export function PublicationTracker({
  clip,
  accounts,
  groups = [],
  isPending,
  onPublish,
  onRecordMetrics,
  onRefreshPublication,
  onSyncMetrics,
  onDeletePublication,
}: {
  clip: Clip;
  accounts: SocialAccount[];
  groups?: SocialAccountGroup[];
  isPending: IsPending;
  onPublish: (clipId: string, data: PublicationCreate[]) => Promise<unknown>;
  onRecordMetrics: (
    publicationId: string,
    data: MetricCreate,
  ) => Promise<unknown>;
  onRefreshPublication: (publicationId: string) => Promise<unknown>;
  onSyncMetrics: (publicationId: string) => Promise<unknown>;
  onDeletePublication: (publicationId: string) => Promise<unknown>;
}) {
  const orderedAccounts = accounts
    .filter((account) => account.is_active)
    .toSorted(
      (first, second) =>
        platformOrder.indexOf(first.platform) -
        platformOrder.indexOf(second.platform),
    );
  const defaultAccount =
    orderedAccounts.find(
      (account) =>
        account.is_default && account.connection_status === "connected",
    ) ??
    orderedAccounts.find(
      (account) => account.connection_status === "connected",
    );
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[] | null>(
    null,
  );
  const effectiveAccountIds =
    selectedAccountIds ?? (defaultAccount ? [defaultAccount.id] : []);
  const selectedAccounts = orderedAccounts.filter((account) =>
    effectiveAccountIds.includes(account.id),
  );
  const publishedCount = clip.publications.filter(
    (publication) => publication.status === "published",
  ).length;
  const connectedCount = orderedAccounts.filter(
    (account) => account.connection_status === "connected",
  ).length;

  if (!clip.final_path) {
    return (
      <section
        className="publication-tracker publishing-locked"
        aria-labelledby="publishing-title"
      >
        <div className="publishing-section-heading">
          <div>
            <span className="eyebrow">DISTRIBUTION</span>
            <h2 id="publishing-title">Publish and measure</h2>
            <p>
              Your destinations and metadata are ready after the final MP4 has
              rendered.
            </p>
          </div>
          <span className="publishing-lock-badge">Export required</span>
        </div>
        <div className="publishing-locked-flow" aria-label="Publishing steps">
          <span className="complete">✓ Edit and preview</span>
          <i aria-hidden="true">→</i>
          <span>2 Render final</span>
          <i aria-hidden="true">→</i>
          <span>3 Choose destination</span>
          <i aria-hidden="true">→</i>
          <span>4 Track results</span>
        </div>
        <small>
          {connectedCount
            ? `${connectedCount} connected destination${connectedCount === 1 ? " is" : "s are"} waiting.`
            : "Connect a social account now, or finish the export first."}
        </small>
      </section>
    );
  }

  return (
    <section className="publication-tracker" aria-labelledby="publishing-title">
      <div className="publishing-section-heading">
        <div>
          <span className="eyebrow">DISTRIBUTION</span>
          <h2 id="publishing-title">Publish and measure</h2>
          <p>
            Send the final clip to several platforms in one click. Uploads run
            in the background while you keep working.
          </p>
        </div>
        <div className="publishing-overview">
          <span>
            <strong>{connectedCount}</strong> connected
          </span>
          <span>
            <strong>{publishedCount}</strong> published
          </span>
        </div>
      </div>

      <div className="publishing-readiness" aria-label="Publishing readiness">
        <span className="complete">
          <i>✓</i> Final MP4 ready
        </span>
        <span className={connectedCount ? "complete" : "attention"}>
          <i>{connectedCount ? "✓" : "!"}</i>
          {connectedCount ? "Destination connected" : "Account setup needed"}
        </span>
        <span className="complete">
          <i>✓</i> Metadata suggested
        </span>
      </div>

      <div className="publishing-layout">
        <div className="publish-composer-shell">
          <div className="destination-heading">
            <div>
              <span>1</span>
              <div>
                <strong>Choose destination</strong>
                <small>Select one or several connected accounts</small>
              </div>
            </div>
            <Link href="/settings/accounts">Manage accounts →</Link>
          </div>

          <div className="destination-presets">
            <label>
              Choose a social group
              <select
                aria-label="Publishing social group"
                defaultValue=""
                onChange={(event) =>
                  setSelectedAccountIds(
                    (
                      groups.find((group) => group.id === event.target.value)
                        ?.account_ids ?? []
                    ).filter((id) =>
                      orderedAccounts.some(
                        (a) =>
                          a.id === id && a.connection_status === "connected",
                      ),
                    ),
                  )
                }
              >
                <option value="">Select a group…</option>
                {groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Or choose a platform
              <select
                aria-label="Publishing platform"
                defaultValue=""
                onChange={(event) =>
                  setSelectedAccountIds(
                    orderedAccounts
                      .filter(
                        (a) =>
                          a.platform === event.target.value &&
                          a.connection_status === "connected",
                      )
                      .map((a) => a.id),
                  )
                }
              >
                <option value="">Select a platform…</option>
                {platformOrder.map((p) => (
                  <option key={p} value={p}>
                    {platformDetails[p].shortLabel}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {orderedAccounts.length ? (
            <div className="destination-picker" aria-label="Publishing account">
              {orderedAccounts.map((account) => {
                const details = platformDetails[account.platform];
                const selected = effectiveAccountIds.includes(account.id);
                const connected = account.connection_status === "connected";
                return (
                  <button
                    key={account.id}
                    type="button"
                    className={`${selected ? "selected" : ""} ${account.platform}`}
                    aria-pressed={selected}
                    aria-label={`${selected ? "Remove" : "Add"} ${account.label} ${selected ? "from" : "to"} publishing destinations`}
                    onClick={() => {
                      if (!connected) return;
                      setSelectedAccountIds((current) =>
                        (current ?? effectiveAccountIds).includes(account.id)
                          ? (current ?? effectiveAccountIds).filter(
                              (id) => id !== account.id,
                            )
                          : [...(current ?? effectiveAccountIds), account.id],
                      );
                    }}
                  >
                    <span className="destination-glyph">{details.glyph}</span>
                    <span>
                      <strong>{account.label}</strong>
                      <small>
                        {details.shortLabel}
                        {account.username ? ` · @${account.username}` : ""}
                      </small>
                    </span>
                    <i className={connected ? "connected" : ""}>
                      {connected ? "Connected" : "Setup"}
                    </i>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="publication-account-required">
              <span className="destination-glyph">+</span>
              <div>
                <strong>Add your first publishing destination</strong>
                <p>
                  Save account defaults once and reuse hashtags, calls to
                  action, campaign links, and reporting currency.
                </p>
              </div>
              <Link className="primary-link" href="/settings/accounts">
                Configure accounts
              </Link>
            </div>
          )}

          {selectedAccounts.length > 0 ? (
            <BatchPublishComposer
              key={effectiveAccountIds.join(",")}
              clip={clip}
              accounts={selectedAccounts}
              pending={isPending(`clip:${clip.id}:publish-batch`)}
              onPublish={onPublish}
            />
          ) : orderedAccounts.length > 0 ? (
            <div className="publication-selection-empty" role="status">
              Select at least one connected destination to prepare this post.
            </div>
          ) : null}
        </div>

        <div className="publication-list">
          <div className="publication-list-heading">
            <div>
              <span>3</span>
              <div>
                <strong>Published destinations</strong>
                <small>Status and latest performance</small>
              </div>
            </div>
            <span>{clip.publications.length} posts</span>
          </div>
          {clip.publications.length === 0 ? (
            <div className="publication-empty">
              <span aria-hidden="true">↗</span>
              <strong>No published destinations yet</strong>
              <small>
                Choose an account, check the suggested copy, and publish when
                you are ready.
              </small>
            </div>
          ) : (
            clip.publications.map((publication) => (
              <PublicationRow
                key={publication.id}
                publication={publication}
                currency={
                  accounts.find(
                    (account) => account.id === publication.social_account_id,
                  )?.currency ?? "EUR"
                }
                isPending={isPending}
                onRecordMetrics={onRecordMetrics}
                onRefresh={onRefreshPublication}
                onSyncMetrics={onSyncMetrics}
                onDelete={onDeletePublication}
              />
            ))
          )}
        </div>
      </div>
    </section>
  );
}

function BatchPublishComposer({
  clip,
  accounts,
  pending,
  onPublish,
}: {
  clip: Clip;
  accounts: SocialAccount[];
  groups?: SocialAccountGroup[];
  pending: boolean;
  onPublish: (clipId: string, data: PublicationCreate[]) => Promise<unknown>;
}) {
  const primaryAccount = accounts[0];
  const metadata = suggestedMetadata(clip, primaryAccount);
  const [title, setTitle] = useState(metadata.title);
  const [description, setDescription] = useState(metadata.description);
  const [copied, setCopied] = useState(false);
  const details = platformDetails[primaryAccount.platform];
  const singlePlatform = accounts.length === 1 ? primaryAccount.platform : null;
  const descriptionLimit = singlePlatform === "x" ? 280 : 5000;

  return (
    <form
      className="publication-form"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const privacyStatus = data.get(
          "privacy_status",
        ) as PublicationCreate["privacy_status"];
        void onPublish(
          clip.id,
          accounts.map((account) => ({
            social_account_id: account.id,
            title: account.platform === "youtube" ? title.slice(0, 100) : title,
            description:
              account.platform === "x"
                ? description.slice(0, 280)
                : description,
            privacy_status: privacyStatus,
          })),
        );
      }}
    >
      <div className="destination-heading composer-heading">
        <div>
          <span>2</span>
          <div>
            <strong>Prepare post</strong>
            <small>
              {accounts.length === 1
                ? `Optimized for ${details.label}`
                : `Shared copy for ${accounts.length} destinations`}
            </small>
          </div>
        </div>
        <span className="destination-count-badge">
          {accounts.length} selected
        </span>
      </div>

      <div
        className="selected-destinations wide"
        aria-label="Selected destinations"
      >
        {accounts.map((account) => (
          <span key={account.id} className={account.platform}>
            <i className={`destination-glyph ${account.platform}`}>
              {platformDetails[account.platform].glyph}
            </i>
            {account.label}
          </span>
        ))}
      </div>

      <label className="wide">
        Post title
        <input
          aria-label="Suggested title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={100}
          required
        />
        <small>{title.length}/100 characters</small>
      </label>
      <label className="wide">
        Description and hashtags
        <textarea
          aria-label="Description and hashtags"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={descriptionLimit}
          rows={6}
        />
        <small>
          {description.length}/{descriptionLimit} characters
        </small>
      </label>
      <div className="publication-form-row wide">
        <label>
          Visibility
          <select name="privacy_status" defaultValue="public">
            <option value="public">
              {singlePlatform === "facebook" ||
              singlePlatform === "instagram" ||
              !singlePlatform
                ? "Platform default"
                : "Public"}
            </option>
            {singlePlatform === "youtube" && (
              <option value="unlisted">Unlisted</option>
            )}
            {singlePlatform === "tiktok" && (
              <option value="friends">Friends</option>
            )}
            {singlePlatform &&
              ["youtube", "tiktok"].includes(singlePlatform) && (
                <option value="private">Private</option>
              )}
          </select>
        </label>
        <button
          type="button"
          className="copy-button"
          onClick={() => {
            void navigator.clipboard?.writeText(description);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          }}
        >
          {copied ? "Copied ✓" : "Copy post text"}
        </button>
      </div>
      <button className="publish-primary-action wide" disabled={pending}>
        <span className="publish-stack" aria-hidden="true">
          {accounts.slice(0, 3).map((account) => (
            <i
              key={account.id}
              className={`destination-glyph ${account.platform}`}
            >
              {platformDetails[account.platform].glyph}
            </i>
          ))}
        </span>
        {pending
          ? "Adding uploads to the queue…"
          : accounts.length === 1
            ? `Publish to ${details.label}`
            : `Publish to ${accounts.length} destinations`}
        <i aria-hidden="true">→</i>
      </button>
      <small className="publish-assurance wide">
        Uploads continue in the background. You can edit another clip while each
        destination reports progress here.
      </small>
    </form>
  );
}

function PublicationRow({
  publication,
  currency,
  isPending,
  onRecordMetrics,
  onRefresh,
  onSyncMetrics,
  onDelete,
}: {
  publication: Publication;
  currency: string;
  isPending: IsPending;
  onRecordMetrics: (
    publicationId: string,
    data: MetricCreate,
  ) => Promise<unknown>;
  onRefresh: (publicationId: string) => Promise<unknown>;
  onSyncMetrics: (publicationId: string) => Promise<unknown>;
  onDelete: (publicationId: string) => Promise<unknown>;
}) {
  const latest = publication.metric_snapshots.at(-1);
  const refreshPending = isPending(`publication:${publication.id}:refresh`);
  const syncPending = isPending(`publication:${publication.id}:sync`);
  const deletePending = isPending(`publication:${publication.id}:delete`);
  const metricsPending = isPending(`publication:${publication.id}:metrics`);
  const details = platformDetails[publication.platform];
  const supportsAutomaticMetrics = [
    "youtube",
    "instagram",
    "facebook",
  ].includes(publication.platform);

  return (
    <article className={`publication-row ${publication.status}`}>
      <div className="publication-row-heading">
        <div className={`publication-platform-icon ${publication.platform}`}>
          {details.glyph}
        </div>
        <div className="publication-row-identity">
          <span className={`publication-status ${publication.status}`}>
            <i />{" "}
            {publication.status === "queued" ? "uploading" : publication.status}
          </span>
          <strong>{publication.title || "Published clip"}</strong>
          <small>
            {details.label}
            {publication.account_label ? ` · ${publication.account_label}` : ""}
            {publication.account_username
              ? ` · @${publication.account_username}`
              : ""}
          </small>
        </div>
        <div className="publication-row-menu">
          {publication.post_url && publication.status === "published" && (
            <a href={publication.post_url} target="_blank" rel="noreferrer">
              View post ↗
            </a>
          )}
          <button
            type="button"
            disabled={deletePending}
            aria-label={`Remove ${details.label} publication`}
            onClick={() => {
              if (
                window.confirm(
                  "Remove this publication and its metric history?",
                )
              )
                void onDelete(publication.id);
            }}
          >
            {deletePending ? "…" : "×"}
          </button>
        </div>
      </div>

      {publication.status === "queued" && (
        <div className="publication-progress queued" role="status">
          <span>
            <i />
          </span>
          <p>
            <strong>Uploading in the background</strong>
            You can keep editing. This card updates automatically when the
            platform receives the clip.
          </p>
        </div>
      )}
      {publication.status === "processing" && (
        <div className="publication-progress" role="status">
          <span>
            <i />
          </span>
          <p>
            <strong>Platform processing is underway</strong>
            ReachCut checks automatically, or you can refresh now.
          </p>
          <button
            type="button"
            disabled={refreshPending}
            onClick={() => void onRefresh(publication.id)}
          >
            {refreshPending ? "Checking…" : "Refresh status"}
          </button>
        </div>
      )}
      {publication.status === "failed" && (
        <div className="publication-progress failed" role="alert">
          <span>!</span>
          <p>
            <strong>Publishing failed</strong>
            {publication.error ||
              "The provider did not return a saved error. Open Accounts to check the connection, then review the API logs for this attempt."}
            <small>Attempt: {publication.id}</small>
          </p>
        </div>
      )}

      {latest ? (
        <div className="publication-summary">
          <span>
            <strong>{latest.views.toLocaleString()}</strong> views
          </span>
          <span>
            <strong>{latest.likes.toLocaleString()}</strong> likes
          </span>
          <span>
            <strong>
              {new Intl.NumberFormat("en", {
                style: "currency",
                currency: latest.currency,
              }).format(latest.revenue)}
            </strong>
            revenue
          </span>
        </div>
      ) : publication.status === "published" ? (
        <div className="publication-awaiting-metrics">
          Published successfully · performance data has not been recorded yet.
        </div>
      ) : null}

      {publication.status === "published" && (
        <div className="publication-row-actions">
          {publication.platform === "youtube" && (
            <button
              type="button"
              disabled={refreshPending}
              onClick={() => void onRefresh(publication.id)}
            >
              {refreshPending ? "Checking…" : "Check status"}
            </button>
          )}
          {supportsAutomaticMetrics && (
            <button
              type="button"
              disabled={syncPending}
              onClick={() => void onSyncMetrics(publication.id)}
            >
              {syncPending ? "Syncing…" : "Sync views"}
            </button>
          )}
          <details className="metrics-entry">
            <summary>{latest ? "Update metrics" : "Add metrics"}</summary>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                const watchTime = String(data.get("watch_time_seconds") ?? "");
                void onRecordMetrics(publication.id, {
                  views: metricValue(data, "views"),
                  likes: metricValue(data, "likes"),
                  comments: metricValue(data, "comments"),
                  shares: metricValue(data, "shares"),
                  watch_time_seconds: watchTime ? Number(watchTime) : null,
                  followers_gained: metricValue(data, "followers_gained"),
                  affiliate_clicks: metricValue(data, "affiliate_clicks"),
                  conversions: metricValue(data, "conversions"),
                  revenue: metricValue(data, "revenue"),
                  currency: String(data.get("currency") || "EUR").toUpperCase(),
                });
              }}
            >
              {[
                ["views", "Views"],
                ["likes", "Likes"],
                ["comments", "Comments"],
                ["shares", "Shares"],
                ["followers_gained", "Followers gained"],
                ["affiliate_clicks", "Affiliate clicks"],
                ["conversions", "Conversions"],
              ].map(([name, label]) => (
                <label key={name}>
                  {label}
                  <input
                    name={name}
                    type="number"
                    min="0"
                    defaultValue={
                      latest?.[name as keyof typeof latest] as
                        number | undefined
                    }
                  />
                </label>
              ))}
              <label>
                Watch time (seconds)
                <input
                  name="watch_time_seconds"
                  type="number"
                  min="0"
                  step="0.1"
                  defaultValue={latest?.watch_time_seconds ?? ""}
                />
              </label>
              <label>
                Revenue
                <input
                  name="revenue"
                  type="number"
                  min="0"
                  step="0.01"
                  defaultValue={latest?.revenue ?? 0}
                />
              </label>
              <label>
                Currency
                <input
                  name="currency"
                  minLength={3}
                  maxLength={3}
                  defaultValue={latest?.currency ?? currency}
                  required
                />
              </label>
              <button className="secondary" disabled={metricsPending}>
                {metricsPending ? "Saving…" : "Save snapshot"}
              </button>
            </form>
            <small>
              Save current cumulative totals. Every update remains in the
              performance history.
            </small>
          </details>
        </div>
      )}

      {latest && (
        <small className="snapshot-freshness">
          Updated{" "}
          {new Intl.DateTimeFormat("en", { dateStyle: "medium" }).format(
            new Date(latest.recorded_at),
          )}
          {publication.metric_snapshots.length > 1
            ? ` · ${publication.metric_snapshots.length} snapshots`
            : ""}
        </small>
      )}
    </article>
  );
}

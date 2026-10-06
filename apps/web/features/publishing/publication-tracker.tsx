"use client";

import Link from "next/link";
import { useState } from "react";

import type { Project, SocialAccount } from "../../lib/contracts";
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
  isPending,
  onPublish,
  onRecordMetrics,
  onRefreshPublication,
  onSyncMetrics,
  onDeletePublication,
}: {
  clip: Clip;
  accounts: SocialAccount[];
  isPending: IsPending;
  onPublish: (clipId: string, data: PublicationCreate) => Promise<unknown>;
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
    orderedAccounts.find((account) => account.is_default) ?? orderedAccounts[0];
  const [accountId, setAccountId] = useState("");
  const selectedAccount =
    orderedAccounts.find((account) => account.id === accountId) ??
    defaultAccount;
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
            Send the final clip to a connected account, then monitor views and
            revenue from the same workspace.
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
                <small>Where should this version go?</small>
              </div>
            </div>
            <Link href="/settings/accounts">Manage accounts →</Link>
          </div>

          {orderedAccounts.length ? (
            <div className="destination-picker" aria-label="Publishing account">
              {orderedAccounts.map((account) => {
                const details = platformDetails[account.platform];
                const selected = account.id === selectedAccount?.id;
                const connected = account.connection_status === "connected";
                return (
                  <button
                    key={account.id}
                    type="button"
                    className={`${selected ? "selected" : ""} ${account.platform}`}
                    aria-pressed={selected}
                    onClick={() => setAccountId(account.id)}
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

          {selectedAccount && (
            <PublishComposer
              key={selectedAccount.id}
              clip={clip}
              account={selectedAccount}
              pending={isPending(`clip:${clip.id}:publish`)}
              onPublish={onPublish}
            />
          )}
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

function PublishComposer({
  clip,
  account,
  pending,
  onPublish,
}: {
  clip: Clip;
  account: SocialAccount;
  pending: boolean;
  onPublish: (clipId: string, data: PublicationCreate) => Promise<unknown>;
}) {
  const metadata = suggestedMetadata(clip, account);
  const [title, setTitle] = useState(metadata.title);
  const [description, setDescription] = useState(metadata.description);
  const [copied, setCopied] = useState(false);
  const connected = account.connection_status === "connected";
  const details = platformDetails[account.platform];
  const descriptionLimit = account.platform === "x" ? 280 : 5000;

  return (
    <form
      className="publication-form"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        void onPublish(clip.id, {
          social_account_id: account.id,
          title,
          description,
          privacy_status: data.get(
            "privacy_status",
          ) as PublicationCreate["privacy_status"],
        });
      }}
    >
      <div className="destination-heading composer-heading">
        <div>
          <span>2</span>
          <div>
            <strong>Prepare post</strong>
            <small>Optimized for {details.label}</small>
          </div>
        </div>
        <span className={`platform-badge ${account.platform}`}>
          {details.label}
        </span>
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
              {account.platform === "facebook" ||
              account.platform === "instagram"
                ? "Platform default"
                : "Public"}
            </option>
            {account.platform === "youtube" && (
              <option value="unlisted">Unlisted</option>
            )}
            {account.platform === "tiktok" && (
              <option value="friends">Friends</option>
            )}
            {["youtube", "tiktok"].includes(account.platform) && (
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
      {!connected && (
        <div className="publication-connection-warning wide">
          <span>!</span>
          <p>
            <strong>{account.label} is not connected.</strong>
            Complete account setup before publishing.
          </p>
          <Link href="/settings/accounts">Open settings</Link>
        </div>
      )}
      <button
        className="publish-primary-action wide"
        disabled={pending || !connected}
      >
        <span className={`destination-glyph ${account.platform}`}>
          {details.glyph}
        </span>
        {pending
          ? `Publishing to ${details.shortLabel}…`
          : `Publish to ${details.label}`}
        <i aria-hidden="true">→</i>
      </button>
      <small className="publish-assurance wide">
        ReachCut uploads the rendered MP4, applies this copy, and saves the post
        URL for performance tracking.
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

  return (
    <article className={`publication-row ${publication.status}`}>
      <div className="publication-row-heading">
        <div className={`publication-platform-icon ${publication.platform}`}>
          {details.glyph}
        </div>
        <div className="publication-row-identity">
          <span className={`publication-status ${publication.status}`}>
            <i /> {publication.status}
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
            Check the account connection and try publishing again.
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
            <>
              <button
                type="button"
                disabled={refreshPending}
                onClick={() => void onRefresh(publication.id)}
              >
                {refreshPending ? "Checking…" : "Check status"}
              </button>
              <button
                type="button"
                disabled={syncPending}
                onClick={() => void onSyncMetrics(publication.id)}
              >
                {syncPending ? "Syncing…" : "Sync views"}
              </button>
            </>
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

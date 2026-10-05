"use client";

import { useState } from "react";
import Link from "next/link";

import type { Project, SocialAccount } from "../../lib/contracts";
import type { MetricCreate, Platform, PublicationCreate } from "./api";

type Clip = Project["clips"][number];
type Publication = Clip["publications"][number];

const platformDetails: Record<Platform, { label: string }> = {
  youtube: {
    label: "YouTube Shorts",
  },
  tiktok: { label: "TikTok" },
  instagram: {
    label: "Instagram Reels",
  },
  facebook: {
    label: "Facebook Reels",
  },
  x: { label: "X" },
};
const platformOrder: Platform[] = [
  "youtube",
  "tiktok",
  "instagram",
  "facebook",
  "x",
];

function suggestedMetadata(clip: Clip, account: SocialAccount | undefined) {
  const platform = account?.platform ?? "youtube";
  const title =
    clip.plan.suggested_title ?? clip.plan.hook?.text ?? "New short clip";
  const hashtags = [
    ...new Set([...clip.plan.hashtags, ...(account?.default_hashtags ?? [])]),
  ].join(" ");
  const additions = [
    hashtags,
    account?.default_cta,
    account?.default_campaign_url,
  ].filter(Boolean);
  const description = [title, ...additions].join("\n\n");
  if (platform === "x") {
    return {
      title,
      description: description.slice(0, 280),
    };
  }
  if (platform === "youtube") {
    return {
      title: title.slice(0, 100),
      description,
    };
  }
  return { title, description };
}

function metricValue(data: FormData, name: string): number {
  return Number(data.get(name)) || 0;
}

export function PublicationTracker({
  clip,
  accounts,
  busy,
  onPublish,
  onRecordMetrics,
  onRefreshPublication,
  onSyncMetrics,
  onDeletePublication,
}: {
  clip: Clip;
  accounts: SocialAccount[];
  busy: boolean;
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
    .slice()
    .sort(
      (first, second) =>
        platformOrder.indexOf(first.platform) -
        platformOrder.indexOf(second.platform),
    );
  const defaultAccount =
    orderedAccounts.find((account) => account.is_default) ?? orderedAccounts[0];
  const [accountId, setAccountId] = useState("");
  const selectedAccount =
    accounts.find((account) => account.id === accountId) ?? defaultAccount;
  const platform = selectedAccount?.platform ?? "youtube";
  const metadata = suggestedMetadata(clip, selectedAccount);

  if (!clip.final_path) {
    return (
      <div className="publication-tracker muted-tracker">
        <strong>Publishing</strong>
        <small>
          Approve and render the final clip to prepare it for publishing.
        </small>
      </div>
    );
  }

  return (
    <div className="publication-tracker">
      <details>
        <summary>Publish and track performance</summary>
        <div className="publishing-layout">
          {selectedAccount ? (
            <form
              className="publication-form"
              action={async (data) => {
                await onPublish(clip.id, {
                  social_account_id: String(data.get("social_account_id")),
                  title: String(data.get("title")),
                  description: String(data.get("description")),
                  privacy_status: data.get(
                    "privacy_status",
                  ) as PublicationCreate["privacy_status"],
                });
              }}
            >
              <div className="publishing-heading">
                <div>
                  <span className="eyebrow">PUBLISH ASSISTANT</span>
                  <strong>Publish this clip with Clipper</strong>
                </div>
                <span>{platformDetails[platform].label}</span>
              </div>
              <input
                type="hidden"
                name="social_account_id"
                value={selectedAccount.id}
              />
              <label className="wide">
                Publishing account
                <select
                  value={selectedAccount.id}
                  onChange={(event) => setAccountId(event.target.value)}
                >
                  {orderedAccounts.map((account) => (
                    <option value={account.id} key={account.id}>
                      {account.label} ·{" "}
                      {platformDetails[account.platform].label}
                      {account.is_default ? " · default" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Suggested title
                <input
                  key={`title-${selectedAccount.id}`}
                  name="title"
                  defaultValue={metadata.title}
                  maxLength={100}
                  required
                />
              </label>
              <label className="wide">
                Description and hashtags
                <textarea
                  key={`description-${selectedAccount.id}`}
                  name="description"
                  defaultValue={metadata.description}
                  maxLength={5000}
                  rows={4}
                />
              </label>
              <button
                type="button"
                className="copy-button"
                onClick={() =>
                  void navigator.clipboard?.writeText(metadata.description)
                }
              >
                Copy suggested text
              </button>
              <label>
                Visibility
                {platform === "tiktok" ? (
                  <select name="privacy_status" defaultValue="public">
                    <option value="public">Public</option>
                    <option value="friends">Friends</option>
                    <option value="private">Only me</option>
                  </select>
                ) : platform === "youtube" ? (
                  <select name="privacy_status" defaultValue="public">
                    <option value="public">Public</option>
                    <option value="unlisted">Unlisted</option>
                    <option value="private">Private</option>
                  </select>
                ) : (
                  <select name="privacy_status" defaultValue="public">
                    <option value="public">Platform default</option>
                  </select>
                )}
              </label>
              <button
                className="primary-button"
                disabled={
                  busy || selectedAccount.connection_status !== "connected"
                }
              >
                {busy ? "Publishing…" : "Publish with Clipper"}
              </button>
              {selectedAccount.connection_status !== "connected" ? (
                <small>
                  Connect this account in Settings before publishing.
                </small>
              ) : (
                <small>
                  Clipper uploads the rendered video, applies this metadata, and
                  saves the resulting post URL automatically.
                </small>
              )}
            </form>
          ) : (
            <div className="publication-form account-required">
              <span className="eyebrow">ACCOUNT SETUP REQUIRED</span>
              <strong>Configure a publishing destination first</strong>
              <p>
                Add your social account once, including default hashtags, CTA,
                campaign link, and reporting currency.
              </p>
              <Link className="primary-link" href="/settings/accounts">
                Configure social accounts
              </Link>
            </div>
          )}
          <div className="publication-list">
            {clip.publications.length === 0 ? (
              <div className="publication-empty">
                <strong>No posts recorded yet</strong>
                <small>
                  Publish the clip with Clipper to begin tracking results.
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
                  busy={busy}
                  onRecordMetrics={onRecordMetrics}
                  onRefresh={onRefreshPublication}
                  onSyncMetrics={onSyncMetrics}
                  onDelete={onDeletePublication}
                />
              ))
            )}
          </div>
        </div>
      </details>
    </div>
  );
}

function PublicationRow({
  publication,
  currency,
  busy,
  onRecordMetrics,
  onRefresh,
  onSyncMetrics,
  onDelete,
}: {
  publication: Publication;
  currency: string;
  busy: boolean;
  onRecordMetrics: (
    publicationId: string,
    data: MetricCreate,
  ) => Promise<unknown>;
  onRefresh: (publicationId: string) => Promise<unknown>;
  onSyncMetrics: (publicationId: string) => Promise<unknown>;
  onDelete: (publicationId: string) => Promise<unknown>;
}) {
  const latest = publication.metric_snapshots.at(-1);

  return (
    <article className="publication-row">
      <div className="publication-row-heading">
        <div>
          <span className={`platform-badge ${publication.platform}`}>
            {platformDetails[publication.platform].label}
          </span>
          <strong>{publication.title || "Published clip"}</strong>
          {publication.account_label && (
            <small>
              {publication.account_label}
              {publication.account_username
                ? ` · @${publication.account_username}`
                : ""}
            </small>
          )}
        </div>
        <div>
          {publication.post_url && publication.status === "published" && (
            <a href={publication.post_url} target="_blank" rel="noreferrer">
              View post ↗
            </a>
          )}
          {publication.status === "processing" && (
            <button
              className="refresh-button"
              type="button"
              disabled={busy}
              onClick={() => void onRefresh(publication.id)}
            >
              Refresh status
            </button>
          )}
          {publication.status === "published" &&
            publication.platform === "youtube" && (
              <>
                <button
                  className="refresh-button"
                  type="button"
                  disabled={busy}
                  onClick={() => void onRefresh(publication.id)}
                >
                  Check status
                </button>
                <button
                  className="refresh-button"
                  type="button"
                  disabled={busy}
                  onClick={() => void onSyncMetrics(publication.id)}
                >
                  Sync views
                </button>
              </>
            )}
          <button
            type="button"
            disabled={busy}
            aria-label={`Remove ${platformDetails[publication.platform].label} publication`}
            onClick={() => {
              if (
                window.confirm(
                  "Remove this publication and its metric history?",
                )
              )
                void onDelete(publication.id);
            }}
          >
            ×
          </button>
        </div>
      </div>
      {publication.status === "processing" && (
        <small className="snapshot-freshness">
          Platform processing is still underway. Clipper checks automatically.
        </small>
      )}
      {publication.status === "failed" && (
        <small className="snapshot-freshness">
          The platform reported that publishing failed.
        </small>
      )}
      {latest && (
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
            </strong>{" "}
            revenue
          </span>
        </div>
      )}
      {publication.status === "published" &&
        publication.platform === "youtube" && (
          <small className="snapshot-freshness">
            YouTube views, likes, and comments sync automatically every minute
            while this workspace is open.
          </small>
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
      {publication.status === "published" && (
        <details className="metrics-entry">
          <summary>{latest ? "Update metrics" : "Add first metrics"}</summary>
          <form
            action={async (data) => {
              const watchTime = String(data.get("watch_time_seconds") ?? "");
              await onRecordMetrics(publication.id, {
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
                    latest?.[name as keyof typeof latest] as number | undefined
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
            <button className="secondary" disabled={busy}>
              Save snapshot
            </button>
          </form>
          <small>
            Enter the current cumulative totals. Each update is saved as a new
            snapshot so performance history is preserved.
          </small>
        </details>
      )}
    </article>
  );
}

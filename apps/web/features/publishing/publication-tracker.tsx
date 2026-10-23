"use client";
import type { PlatformCopy } from "./growth-api";
import { captionWithTags } from "./publishing-copy";

import Link from "next/link";
import { ActionLink } from "../../components/action-link";
import {
  getPostManagement,
  type PublishingReport,
} from "./post-management-api";
import { useEffect, useState } from "react";

import type {
  Project,
  SocialAccount,
  SocialAccountGroup,
} from "../../lib/contracts";
import {
  loadPublishingSelection,
  savePublishingSelection,
  socialConnectUrl,
  type MetricCreate,
  type Platform,
  type PublicationCreate,
} from "./api";

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
  const description = [
    clip.plan.suggested_description || title,
    ...additions,
  ].join("\n\n");
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
  preferredAccountIds = [],
  preparing = false,
  preparationMessage,
  growthCopy = [],
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
  preferredAccountIds?: string[];
  preparing?: boolean;
  preparationMessage?: string;
  growthCopy?: PlatformCopy[];
  isPending: IsPending;
  onPublish: (
    clipId: string,
    data: PublicationCreate[],
  ) => Promise<PublishingReport | undefined>;
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
  useEffect(() => {
    let active = true;
    Promise.resolve(loadPublishingSelection(clip.id)).then((saved) => {
      if (active && saved) setSelectedAccountIds(saved);
    });
    return () => {
      active = false;
    };
  }, [clip.id]);
  function choose(ids: string[]) {
    setSelectedAccountIds(ids);
    savePublishingSelection(clip.id, ids);
  }
  const preferred = preferredAccountIds.filter((id) =>
    orderedAccounts.some(
      (a) => a.id === id && a.connection_status === "connected",
    ),
  );
  const effectiveAccountIds =
    selectedAccountIds ??
    (preferredAccountIds.length
      ? preferred
      : clip.publications.some((post) => post.status === "published")
        ? [
            ...new Set(
              clip.publications
                .filter(
                  (post) =>
                    post.status === "published" &&
                    orderedAccounts.some(
                      (account) =>
                        account.id === post.social_account_id &&
                        account.connection_status === "connected",
                    ),
                )
                .map((post) => post.social_account_id!),
            ),
          ]
        : defaultAccount
          ? [defaultAccount.id]
          : []);
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

      {preparing && (
        <p role="status">
          The project pipeline is preparing the latest publishing copy.
          Publishing will be available when it finishes.
        </p>
      )}
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
            <ActionLink href="/settings/accounts" icon="⚙">
              Manage accounts
            </ActionLink>
          </div>

          <div className="destination-presets">
            <label>
              Choose a social group
              <select
                aria-label="Publishing social group"
                defaultValue=""
                onChange={(event) =>
                  choose(
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
                  choose(
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
                      choose(
                        effectiveAccountIds.includes(account.id)
                          ? effectiveAccountIds.filter(
                              (id) => id !== account.id,
                            )
                          : [...effectiveAccountIds, account.id],
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
              growthCopy={growthCopy}
              key={effectiveAccountIds.join(",")}
              clip={clip}
              accounts={selectedAccounts}
              pending={isPending(`clip:${clip.id}:publish-batch`)}
              preparing={preparing}
              preparationMessage={preparationMessage}
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
            <ActionLink href={`/publishing/posts?clip=${clip.id}`} icon="↗">
              Manage social posts
            </ActionLink>
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
  growthCopy,
  clip,
  accounts,
  pending,
  preparing,
  preparationMessage,
  onPublish,
}: {
  growthCopy: PlatformCopy[];
  clip: Clip;
  accounts: SocialAccount[];
  groups?: SocialAccountGroup[];
  pending: boolean;
  preparing: boolean;
  preparationMessage?: string;
  onPublish: (
    clipId: string,
    data: PublicationCreate[],
  ) => Promise<PublishingReport | undefined>;
}) {
  const primaryAccount = accounts[0];
  const metadata = suggestedMetadata(clip, primaryAccount);
  const [title, setTitle] = useState(metadata.title);
  const [description, setDescription] = useState(metadata.description);
  const primaryCopy = growthCopy.find(
    (copy) => copy.platform === primaryAccount.platform,
  );
  const displayedTitle = primaryCopy?.title ?? title;
  const displayedDescription = primaryCopy
    ? captionWithTags(primaryCopy.caption, primaryCopy.hashtags)
    : description;
  const [copied, setCopied] = useState(false);
  const [report, setReport] = useState<PublishingReport>();
  const [submitError, setSubmitError] = useState("");
  const details = platformDetails[primaryAccount.platform];
  const singlePlatform = accounts.length === 1 ? primaryAccount.platform : null;
  const descriptionLimit = singlePlatform === "x" ? 280 : 5000;
  const existing = accounts.filter((account) =>
    clip.publications.some(
      (post) =>
        post.social_account_id === account.id && post.status === "published",
    ),
  );

  const existingIds = clip.publications
    .filter(
      (post) =>
        post.status === "published" &&
        accounts.some((account) => account.id === post.social_account_id),
    )
    .map((post) => post.id)
    .join(",");
  const [connectionNotices, setConnectionNotices] = useState<
    {
      id: string;
      accountId: string | null;
      platform: string;
      message: string;
      reconnect: boolean;
      update?: boolean;
      working?: boolean;
    }[]
  >([]);
  const [connectionReload, setConnectionReload] = useState(0);
  const [checkedIds, setCheckedIds] = useState("");
  useEffect(() => {
    let active = true;
    if (!existingIds) return;
    void Promise.all(
      existingIds.split(",").map(async (id) => {
        try {
          const data = await getPostManagement(id);
          return {
            id,
            message: !data.capabilities.update
              ? data.capabilities.explanation
              : data.capabilities.reconnect_required
                ? (data.capabilities.connection_issue ??
                  "Reconnect in Accounts")
                : data.operation?.state === "working"
                  ? "An update is already in progress. Check the original post before retrying."
                  : "",
            update: data.capabilities.update,
            working: data.operation?.state === "working",
            reconnect: data.capabilities.reconnect_required,
          };
        } catch {
          return {
            id,
            message:
              "Could not check post permissions. Retry or open Manage social posts.",
            reconnect: false,
          };
        }
      }),
    ).then((results) => {
      if (active) {
        setCheckedIds(existingIds);
        setConnectionNotices(
          results
            .filter((result) => result.message)
            .map((result) => {
              const post = clip.publications.find(
                (post) => post.id === result.id,
              )!;
              return {
                ...result,
                accountId: post.social_account_id,
                platform: post.platform,
              };
            }),
        );
      }
    });
    return () => {
      active = false;
    };
  }, [existingIds, clip.publications, connectionReload]);

  const actionable = accounts.filter((account) => {
    const posts = clip.publications.filter(
      (post) => post.social_account_id === account.id,
    );
    if (
      posts.some((post) =>
        ["queued", "processing", "uncertain", "deferred"].includes(post.status),
      )
    )
      return false;
    return !connectionNotices.some((issue) => issue.accountId === account.id);
  });
  const updateCount = actionable.filter((account) =>
    existing.some((item) => item.id === account.id),
  ).length;
  const newCount = actionable.length - updateCount;

  return (
    <form
      className="publication-form"
      onSubmit={async (event) => {
        event.preventDefault();
        setReport(undefined);
        setSubmitError("");
        const data = new FormData(event.currentTarget);
        const privacyStatus = data.get(
          "privacy_status",
        ) as PublicationCreate["privacy_status"];
        try {
          const result = await onPublish(
            clip.id,
            accounts.map((account) => {
              const copy = growthCopy.find(
                (p) => p.platform === account.platform,
              );
              const postTitle = copy?.title ?? title;
              const postDescription = copy
                ? captionWithTags(copy.caption, copy.hashtags)
                : description;
              return {
                social_account_id: account.id,
                title: postTitle.slice(0, 100),
                description:
                  account.platform === "x"
                    ? postDescription.slice(0, 280)
                    : postDescription,
                privacy_status: privacyStatus,
              };
            }),
          );
          setReport(result);
        } catch (error) {
          setSubmitError(
            error instanceof Error
              ? error.message
              : "Could not save publishing changes",
          );
        }
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

      {growthCopy.length > 0 && (
        <div className="wide" aria-label="Reviewed platform copy">
          <p>
            Each destination uses the AI publishing copy below. The project
            pipeline prepares this automatically; advanced overrides are
            available in the growth brief.
          </p>
          {accounts.map((account) => {
            const copy = growthCopy.find(
              (p) => p.platform === account.platform,
            );
            return copy ? (
              <article key={account.id}>
                <strong>
                  {account.label}: {copy.title}
                </strong>
                <p>
                  {captionWithTags(copy.caption, copy.hashtags).slice(
                    0,
                    account.platform === "x" ? 280 : undefined,
                  )}
                </p>
              </article>
            ) : (
              <p key={account.id}>{account.label} uses shared copy.</p>
            );
          })}
        </div>
      )}
      <label className="wide">
        Post title
        <input
          disabled={accounts.every((a) =>
            growthCopy.some((p) => p.platform === a.platform),
          )}
          aria-label="Suggested title"
          value={displayedTitle}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={100}
          required
        />
        <small>{displayedTitle.length}/100 characters</small>
      </label>
      <label className="wide">
        Description and hashtags
        <textarea
          disabled={accounts.every((a) =>
            growthCopy.some((p) => p.platform === a.platform),
          )}
          aria-label="Description and hashtags"
          value={displayedDescription}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={descriptionLimit}
          rows={6}
        />
        <small>
          {displayedDescription.length}/{descriptionLimit} characters
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
            const copy = growthCopy.find(
              (p) => p.platform === primaryAccount.platform,
            );
            const text = copy
              ? captionWithTags(copy.caption, copy.hashtags)
              : description;
            void navigator.clipboard?.writeText(
              primaryAccount.platform === "x" ? text.slice(0, 280) : text,
            );
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          }}
        >
          {copied ? "Copied ✓" : "Copy post text"}
        </button>
      </div>
      <section
        className="wide destination-action-summary"
        aria-label="Actions for selected destinations"
      >
        <h3>What happens for each destination</h3>
        {accounts.map((account) => {
          const post = clip.publications
            .filter(
              (post) =>
                post.social_account_id === account.id &&
                post.status === "published",
            )
            .toSorted(
              (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
            )[0];
          const issue = connectionNotices.find(
            (issue) => issue.accountId === account.id,
          );
          const copy = growthCopy.find(
            (item) => item.platform === account.platform,
          );
          const same =
            post &&
            (copy?.caption ?? description) === post.description &&
            (account.platform !== "youtube" ||
              (copy?.title ?? title) === post.title);
          const blocked = clip.publications.find(
            (item) =>
              item.social_account_id === account.id &&
              ["queued", "processing", "uncertain", "deferred"].includes(
                item.status,
              ),
          );
          return (
            <article key={account.id}>
              <strong>
                {platformDetails[account.platform].shortLabel} · {account.label}
              </strong>
              <p>
                {blocked
                  ? `Upload ${blocked.status} — check its status below before retrying.`
                  : issue
                    ? issue.message
                    : post
                      ? same
                        ? "Already using this copy. No changes will be sent."
                        : "Update the existing post. Keep its engagement and metrics."
                      : "Publish a new post to this account."}
              </p>
              {issue?.update === false && (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      void navigator.clipboard?.writeText(
                        copy
                          ? captionWithTags(copy.caption, copy.hashtags)
                          : description,
                      );
                      setCopied(true);
                    }}
                  >
                    Copy latest caption
                  </button>
                  {post?.post_url && (
                    <a
                      className="action-link"
                      href={post.post_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open original{" "}
                      {platformDetails[account.platform].shortLabel} post ↗
                    </a>
                  )}
                  <small>
                    Saved upload label: {post?.title}. This label is not a
                    separate title on{" "}
                    {platformDetails[account.platform].shortLabel}.
                  </small>
                </>
              )}
            </article>
          );
        })}
      </section>
      {connectionNotices
        .filter((issue) => issue.update !== false)
        .map((issue) => (
          <div
            className="wide account-health-issue"
            key={issue.id}
            role="alert"
          >
            <p>
              {issue.platform}: {issue.message}
            </p>
            {issue.reconnect && issue.accountId && (
              <a
                className="action-link"
                href={socialConnectUrl(issue.accountId)}
              >
                Reconnect {issue.platform} →
              </a>
            )}
            <button
              type="button"
              onClick={() => setConnectionReload((value) => value + 1)}
            >
              Check again
            </button>
          </div>
        ))}
      <button
        className="publish-primary-action wide"
        disabled={
          pending ||
          preparing ||
          checkedIds !== existingIds ||
          !actionable.length
        }
        aria-busy={pending}
      >
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
          ? "Saving publishing changes…"
          : preparing
            ? (preparationMessage ?? "Preparing publishing copy…")
            : checkedIds !== existingIds
              ? "Checking destination actions…"
              : !actionable.length
                ? "No automatic actions available"
                : updateCount && newCount
                  ? `Update ${updateCount} & publish ${newCount} new`
                  : updateCount
                    ? `Update ${updateCount} existing post${updateCount === 1 ? "" : "s"}`
                    : accounts.length === 1
                      ? `Publish to ${details.label}`
                      : `Publish to ${newCount} destinations`}
        <i aria-hidden="true">→</i>
      </button>
      {preparing && (
        <p className="wide" role="status">
          {preparationMessage ?? "Preparing publishing copy…"}
        </p>
      )}
      {submitError && (
        <p className="wide error" role="alert">
          {submitError}
        </p>
      )}
      {report && (
        <section
          className="wide publishing-results"
          aria-label="Publishing results"
          aria-live="polite"
        >
          <h3>Publishing results</h3>
          {report.outcomes.map((outcome) => (
            <article key={outcome.accountId}>
              <strong>
                {accounts.find((account) => account.id === outcome.accountId)
                  ?.label ?? outcome.platform}{" "}
                ·{" "}
                {outcome.state === "manual"
                  ? "Edit on platform"
                  : outcome.state}
              </strong>
              <p>{outcome.message}</p>
            </article>
          ))}
        </section>
      )}
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
            {publication.status === "queued" ? "queued" : publication.status}
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
            disabled={
              deletePending ||
              ["processing", "uncertain"].includes(publication.status)
            }
            aria-label={`Remove ${details.label} publication`}
            onClick={() => {
              if (
                window.confirm(
                  publication.status === "queued"
                    ? "Cancel this queued upload before it starts?"
                    : "Remove the local entry and metric history? The post will stay on the platform. Use Manage social posts to delete it remotely.",
                )
              )
                void onDelete(publication.id);
            }}
          >
            {deletePending
              ? "…"
              : publication.status === "queued"
                ? "Cancel upload"
                : "Remove local entry"}
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
      {publication.status === "uncertain" && (
        <div className="publication-progress failed" role="alert">
          <span>!</span>
          <div>
            <strong>Verify the existing upload</strong>
            <p>
              {publication.error ||
                "The platform may already have received this video. Check before uploading again."}
            </p>
            {publication.provider_publication_id ? (
              <button
                type="button"
                disabled={refreshPending}
                onClick={() => void onRefresh(publication.id)}
              >
                {refreshPending
                  ? "Checking existing upload…"
                  : "Check existing upload status"}
              </button>
            ) : (
              <p>
                No remote ID was saved. Check the destination directly before
                retrying.
              </p>
            )}
          </div>
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
                  reach: data.get("reach") ? Number(data.get("reach")) : null,
                  sends: data.get("sends") ? Number(data.get("sends")) : null,
                  average_watch_seconds: data.get("average_watch_seconds")
                    ? Number(data.get("average_watch_seconds"))
                    : null,
                  opening_retention_percent: data.get(
                    "opening_retention_percent",
                  )
                    ? Number(data.get("opening_retention_percent"))
                    : null,
                  completion_rate_percent: data.get("completion_rate_percent")
                    ? Number(data.get("completion_rate_percent"))
                    : null,
                  search_views: data.get("search_views")
                    ? Number(data.get("search_views"))
                    : null,
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
              <p>
                Optional growth observations: leave blank when unavailable.
                Retention percentages must use the same definition across posts.
              </p>
              {[
                ["reach", "Accounts reached"],
                ["sends", "Sends"],
                ["average_watch_seconds", "Average watch time (seconds)"],
                [
                  "opening_retention_percent",
                  "Still watching at 3 seconds (%)",
                ],
                ["completion_rate_percent", "Completion rate (%)"],
                ["search_views", "Views from search"],
              ].map(([name, label]) => (
                <label key={name}>
                  {label}
                  <input
                    name={name}
                    type="number"
                    min="0"
                    max={name.endsWith("percent") ? 100 : undefined}
                    step={
                      name.endsWith("percent") ||
                      name === "average_watch_seconds"
                        ? "0.1"
                        : "1"
                    }
                    defaultValue={
                      (latest?.[name as keyof typeof latest] as
                        number | undefined) ?? ""
                    }
                  />
                </label>
              ))}
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

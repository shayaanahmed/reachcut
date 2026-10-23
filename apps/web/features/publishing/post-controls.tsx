"use client";
import { useEffect, useState } from "react";
import type { Project } from "../../lib/contracts";
import { ActionLink } from "../../components/action-link";
import { deletePublication, refreshPublication, socialConnectUrl } from "./api";
import {
  deleteRemotePost,
  getPostManagement,
  publishSeparatePost,
  updateRemotePost,
  type PostManagementData,
} from "./post-management-api";

type Post = Project["clips"][number]["publications"][number];
export function PostControls({
  post,
  revision = "",
  onChanged,
}: {
  post: Post;
  revision?: string;
  onChanged: (project: Project) => void;
}) {
  const [data, setData] = useState<PostManagementData | null>(null);
  const [edit, setEdit] = useState<{
    title: string;
    description: string;
  } | null>(null);
  const title = edit?.title ?? data?.suggested.title ?? "";
  const description = edit?.description ?? data?.suggested.description ?? "";
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmation, setConfirmation] = useState<
    "delete" | "forget" | "new" | null
  >(null);
  useEffect(() => {
    let active = true;
    getPostManagement(post.id)
      .then((result) => {
        if (active) {
          setData(result);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [post.id, post.title, post.description, post.status, revision, reload]);
  async function run(
    action: "update" | "delete" | "forget" | "new" | "refresh",
  ) {
    setBusy(action);
    setError("");
    setNotice("");
    try {
      const updated =
        action === "refresh"
          ? await refreshPublication(post.id)
          : action === "update"
            ? await updateRemotePost(post.id, { title, description })
            : action === "delete"
              ? await deleteRemotePost(post.id)
              : action === "new"
                ? await publishSeparatePost(post.id)
                : await deletePublication(post.id);
      onChanged(updated);
      setConfirmation(null);
      setNotice(
        action === "refresh"
          ? "Existing upload status checked. No new upload was sent."
          : action === "update"
            ? "Existing post updated. Its ID and metrics history are preserved."
            : action === "delete"
              ? "Deleted from the platform. Local history is preserved."
              : action === "new"
                ? "A separate new post is queued. The original remains published."
                : "Local entry removed.",
      );
      if (action !== "forget") setData(await getPostManagement(post.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setReload((value) => value + 1);
    } finally {
      setBusy("");
    }
  }
  const published = post.status === "published";
  return (
    <article
      className="post-control-card"
      aria-label={`${post.platform} ${post.account_label ?? "post"}`}
    >
      <header>
        <div>
          <span className="platform-pill">{post.platform}</span>
          <strong>{post.account_label ?? "Historical account"}</strong>
        </div>
        <span className="post-state">
          {data?.operation?.state === "working"
            ? `${data.operation.action} in progress`
            : data?.capabilities.reconnect_required
              ? "Reconnect required"
              : data?.operation?.state === "failed"
                ? "Action failed"
                : data?.needs_update && published
                  ? data.capabilities.update
                    ? "Changes available"
                    : "Copy available · edit on platform"
                  : published && data
                    ? "Up to date"
                    : post.status}
        </span>
      </header>
      {post.post_url && (
        <a
          className="inline-post-link"
          href={post.post_url}
          target="_blank"
          rel="noreferrer"
        >
          Open original post ↗
        </a>
      )}
      {data ? (
        <p className="muted">{data.capabilities.explanation}</p>
      ) : (
        !error && <p role="status">Loading post tools…</p>
      )}
      {error && !data && (
        <button type="button" onClick={() => setReload((value) => value + 1)}>
          Retry loading post tools
        </button>
      )}
      {data?.capabilities.reconnect_required && (
        <div className="account-health-issue" role="alert">
          <p>{data.capabilities.connection_issue}</p>
          {post.social_account_id && (
            <a
              className="action-link"
              href={socialConnectUrl(post.social_account_id)}
            >
              Reconnect {post.platform} account →
            </a>
          )}
          <ActionLink href="/settings/accounts">Open Accounts</ActionLink>
          <button type="button" onClick={() => setReload((value) => value + 1)}>
            Check connection again
          </button>
        </div>
      )}
      {data?.capabilities.deletion_issue && (
        <div className="account-health-issue" role="status">
          <strong>Deletion needs setup</strong>
          <p>{data.capabilities.deletion_issue}</p>
          {data.capabilities.deletion_reconnect_required &&
            post.social_account_id && (
              <a
                className="action-link"
                href={socialConnectUrl(post.social_account_id)}
              >
                Reconnect for {post.platform} deletion →
              </a>
            )}
          <button type="button" onClick={() => setReload((value) => value + 1)}>
            Check deletion permissions
          </button>
        </div>
      )}
      {data?.hashtag_notice && <p role="status">{data.hashtag_notice}</p>}
      {published && (
        <details className="post-edit-details">
          <summary>Edit publishing details</summary>
          <p>
            Latest pipeline draft · updating preserves the original post and
            metrics.
          </p>
          <details>
            <summary>Currently published copy</summary>
            <strong>{post.title}</strong>
            <p className="preserve-lines">{post.description}</p>
          </details>
          <label>
            Title
            <input
              maxLength={100}
              disabled={!data?.capabilities.title || !!busy}
              value={title}
              onChange={(e) => setEdit({ title: e.target.value, description })}
            />
          </label>
          <label>
            Caption / description
            <textarea
              rows={5}
              maxLength={5000}
              disabled={!data || !!busy}
              readOnly={!data?.capabilities.update}
              value={description}
              onChange={(e) => setEdit({ title, description: e.target.value })}
            />
          </label>
          {data && (
            <button
              type="button"
              disabled={!!busy || !data.capabilities.update}
              onClick={() => {
                setEdit(null);
              }}
            >
              Use latest pipeline copy
            </button>
          )}
          {data && !data.capabilities.update && (
            <button
              type="button"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(description);
                  setNotice(
                    "Latest caption copied. Open the original platform post to paste it.",
                  );
                } catch {
                  setError(
                    "Clipboard unavailable. Select the caption above and copy it manually.",
                  );
                }
              }}
            >
              Copy latest caption
            </button>
          )}
          <button
            type="button"
            className="primary-button"
            aria-busy={busy === "update"}
            disabled={
              !!busy ||
              !data?.capabilities.update ||
              data.capabilities.reconnect_required ||
              data.operation?.state === "working" ||
              !title.trim()
            }
            onClick={() => void run("update")}
          >
            {busy === "update"
              ? "Updating existing post…"
              : "Update existing post"}
          </button>
        </details>
      )}
      <div className="post-management-actions">
        {published && (
          <button
            disabled={
              !!busy ||
              !data?.capabilities.delete ||
              data.capabilities.reconnect_required ||
              data.operation?.state === "working"
            }
            onClick={() => setConfirmation("delete")}
          >
            Delete from {post.platform}
          </button>
        )}
        {published && (
          <button
            disabled={!!busy || data?.operation?.state === "working"}
            onClick={() => setConfirmation("new")}
          >
            Publish as a separate new post
          </button>
        )}
        {!["processing", "uncertain"].includes(post.status) && (
          <button
            disabled={!!busy || data?.operation?.state === "working"}
            onClick={() => setConfirmation("forget")}
          >
            {post.status === "queued"
              ? "Cancel queued upload"
              : "Remove local record"}
          </button>
        )}
      </div>
      {["processing", "uncertain"].includes(post.status) && (
        <p>
          The upload may already exist on the platform. Check its status before
          attempting another upload.
          {post.provider_publication_id && (
            <button
              type="button"
              disabled={!!busy}
              onClick={() => void run("refresh")}
            >
              {busy === "refresh"
                ? "Checking existing upload…"
                : "Check existing upload status"}
            </button>
          )}
        </p>
      )}
      {confirmation && (
        <div
          className="post-confirmation"
          role="group"
          aria-label="Confirm post action"
        >
          <p>
            {confirmation === "delete"
              ? `Delete the actual ${post.platform} post? This cannot be undone. Its local metrics history will remain.`
              : confirmation === "new"
                ? "Create a separate new post? The original post and its engagement will remain."
                : post.status === "queued"
                  ? "Cancel this queued upload before it starts?"
                  : "Remove only this local record and its metrics? The original platform post will remain."}
          </p>
          <button disabled={!!busy} onClick={() => void run(confirmation)}>
            {busy ? "Working…" : "Confirm"}
          </button>
          <button disabled={!!busy} onClick={() => setConfirmation(null)}>
            Keep it
          </button>
        </div>
      )}
      {(error || data?.operation?.error || post.error) && (
        <p role="alert" className="error">
          {error ||
            (data?.operation?.action === "delete" &&
            data.capabilities.deletion_issue
              ? data.capabilities.deletion_issue
              : data?.operation?.error) ||
            post.error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!!data?.history.length && (
        <details>
          <summary>Change history ({data.history.length})</summary>
          {data.history.map((change, i) => (
            <article key={`${change.created_at}:${i}`}>
              <strong>
                {change.action} · {new Date(change.created_at).toLocaleString()}
              </strong>
              <details>
                <summary>View saved before & after</summary>
                <p className="preserve-lines">
                  Before:{" "}
                  {String(
                    change.before.description ?? change.before.status ?? "",
                  )}
                </p>
                <p className="preserve-lines">
                  After:{" "}
                  {String(
                    change.after.description ?? change.after.status ?? "",
                  )}
                </p>
              </details>
            </article>
          ))}
        </details>
      )}
    </article>
  );
}

"use client";
import { useState } from "react";
import Link from "next/link";
import type {
  Project,
  SocialAccount,
  SocialAccountGroup,
} from "../../lib/contracts";
import type { BulkPublishResult } from "./api";
import { DestinationSelector } from "./destination-selector";

export function BulkClipActions({
  project,
  accounts,
  groups,
  pending,
  onApprove,
  onRender,
  onPublish,
}: {
  project: Project;
  accounts: SocialAccount[];
  groups: SocialAccountGroup[];
  pending: boolean;
  onApprove: (id: string, ids: string[] | null) => Promise<unknown>;
  onRender: (id: string) => Promise<unknown>;
  onPublish: (
    id: string,
    ids: string[],
    accounts: string[],
  ) => Promise<BulkPublishResult | undefined>;
}) {
  const [selection, setSelection] = useState<string[]>([]);
  const [destinations, setDestinations] = useState<string[]>([]);
  const [working, setWorking] = useState(false);
  const [result, setResult] = useState<BulkPublishResult | null>(null);
  const [notice, setNotice] = useState("");
  const selected = project.clips.filter((c) => selection.includes(c.id));
  const ready = selected.filter(
    (c) => c.approval_status === "approved" && c.final_path,
  );
  const needsRender = selected.filter(
    (c) => c.approval_status === "approved" && !c.final_path,
  );
  const disabled = pending || working;
  const allReady = project.clips.filter(
    (c) => c.approval_status === "approved" && c.final_path,
  );
  async function publish(ids: string[]) {
    setResult(null);
    setNotice("");
    const published = await onPublish(project.id, ids, destinations);
    if (published) setResult(published);
  }
  async function renderSelection() {
    setWorking(true);
    setNotice("");
    try {
      for (const clip of needsRender) await onRender(clip.id);
      setNotice(
        "Render queue finished. Check each clip’s export status before publishing.",
      );
    } finally {
      setWorking(false);
    }
  }
  return (
    <section className="bulk-distribution" aria-label="Bulk clip publishing">
      <div className="section-heading">
        <div>
          <span className="eyebrow">REVIEW → EXPORT → PUBLISH</span>
          <h2>Publish your clips</h2>
          <p>
            Select clips, approve them together, then send finished exports to
            your channels.
          </p>
        </div>
        <Link href="/settings/accounts">Manage accounts & groups →</Link>
      </div>
      <div className="bulk-clip-list">
        <label className="bulk-select-all">
          <input
            type="checkbox"
            checked={
              selection.length > 0 && selected.length === project.clips.length
            }
            onChange={(e) =>
              setSelection(
                e.target.checked ? project.clips.map((c) => c.id) : [],
              )
            }
          />
          Select all {project.clips.length} clips
        </label>
        {project.clips.map((clip, index) => (
          <label key={clip.id}>
            <input
              type="checkbox"
              checked={selection.includes(clip.id)}
              onChange={(e) =>
                setSelection(
                  e.target.checked
                    ? [...selection, clip.id]
                    : selection.filter((id) => id !== clip.id),
                )
              }
            />
            <span>
              <strong>
                {clip.plan.suggested_title ?? `Clip ${index + 1}`}
              </strong>
              <small>
                {clip.approval_status} ·{" "}
                {clip.final_path ? "Export ready" : "Needs export"}
              </small>
            </span>
            <Link href={`/projects/${project.id}/clips/${clip.id}/publish`}>
              Publish individually →
            </Link>
          </label>
        ))}
      </div>
      <div className="bulk-toolbar">
        <span aria-live="polite">
          {selected.length} selected · {ready.length} ready to publish
        </span>
        <button
          disabled={disabled || !selected.length}
          onClick={async () => {
            const updated = await onApprove(
              project.id,
              selected.map((c) => c.id),
            );
            if (updated) setNotice(`${selected.length} clips approved.`);
          }}
        >
          Approve selected
        </button>
        <button
          disabled={disabled || !project.clips.length}
          onClick={async () => {
            const updated = await onApprove(project.id, null);
            if (updated) setNotice("All generated clips approved.");
          }}
        >
          Approve all
        </button>
        <button
          disabled={disabled || !needsRender.length}
          onClick={() => void renderSelection()}
        >
          {working ? "Rendering…" : `Render selected (${needsRender.length})`}
        </button>
      </div>
      <DestinationSelector
        accounts={accounts}
        groups={groups}
        selected={destinations}
        onChange={setDestinations}
      />
      <div className="bulk-publish-footer">
        <p>
          Public posts · Suggested clip titles, hashtags, and each account’s
          defaults. Already queued or published destinations are skipped.
          Unapproved clips and missing exports are skipped with a reason.
        </p>
        <button
          className="primary-link"
          disabled={disabled || !ready.length || !destinations.length}
          onClick={async () => {
            setResult(null);
            setNotice("");
            const published = await onPublish(
              project.id,
              selected.map((c) => c.id),
              destinations,
            );
            if (published) setResult(published);
          }}
        >
          {pending
            ? "Queuing…"
            : `Publish selected · ${ready.length} clips × ${destinations.length} destinations`}
        </button>
        <button
          disabled={disabled || !allReady.length || !destinations.length}
          onClick={() => void publish(allReady.map((c) => c.id))}
        >
          Publish all ready ({allReady.length})
        </button>
      </div>
      {notice && <p role="status">{notice}</p>}
      {result && (
        <div className="bulk-result" role="status">
          <strong>
            {result.queued} posts queued · {result.skipped.length} skipped
          </strong>
          <p>
            Uploads run in the background. Open a clip’s publishing page to
            follow progress.
          </p>
          {result.skipped.length > 0 && (
            <details>
              <summary>View skipped destinations</summary>
              <ul>
                {result.skipped.map((item) => (
                  <li key={`${item.clip_id}:${item.account_id}`}>
                    {project.clips.find((c) => c.id === item.clip_id)?.plan
                      .suggested_title ?? "Clip"}{" "}
                    →{" "}
                    {accounts.find((a) => a.id === item.account_id)?.label ??
                      "Account"}
                    : {item.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}

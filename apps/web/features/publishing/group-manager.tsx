"use client";

import { useEffect, useState } from "react";
import type { SocialAccount, SocialAccountGroup } from "../../lib/contracts";
import { deleteAccountGroup, listAccountGroups, saveAccountGroup } from "./api";

export function GroupManager({ accounts }: { accounts: SocialAccount[] }) {
  const [groups, setGroups] = useState<SocialAccountGroup[]>([]);
  const [editing, setEditing] = useState<SocialAccountGroup | "new" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    void listAccountGroups()
      .then(setGroups)
      .catch((e: Error) => setError(e.message));
  }, []);
  async function remove(group: SocialAccountGroup) {
    if (
      !window.confirm(
        `Delete “${group.name}”? Accounts and published posts will be kept.`,
      )
    )
      return;
    setPending(true);
    setError(null);
    try {
      await deleteAccountGroup(group.id);
      setGroups(await listAccountGroups());
      if (editing !== "new" && editing?.id === group.id) setEditing(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete group");
    } finally {
      setPending(false);
    }
  }
  return (
    <section
      className="group-manager section-block"
      aria-labelledby="account-groups-title"
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">CHANNEL ORGANIZATION</span>
          <h2 id="account-groups-title">Social account groups</h2>
          <p>
            Build destinations like Religious, Art, or Tech across platforms. An
            account can belong to several groups.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setEditing("new");
            setQuery("");
          }}
          disabled={pending}
        >
          ＋ New group
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!groups.length && (
        <p className="muted">
          No groups yet. Create one to publish to a set of channels in one step.
        </p>
      )}
      <div className="group-grid">
        {groups.map((group) => (
          <article className="group-card" key={group.id}>
            <h3>{group.name}</h3>
            <p>
              {group.description || "A collection of publishing destinations"}
            </p>
            <small>
              {
                group.account_ids.filter((id) =>
                  accounts.some((a) => a.id === id),
                ).length
              }{" "}
              active accounts
            </small>
            <div className="inline-actions">
              <button
                disabled={pending}
                onClick={() => {
                  setEditing(group);
                  setQuery("");
                }}
              >
                Edit group
              </button>
              <button disabled={pending} onClick={() => void remove(group)}>
                Delete
              </button>
            </div>
          </article>
        ))}
      </div>
      {editing && (
        <form
          className="group-editor"
          key={editing === "new" ? "new" : editing.id}
          action={async (data) => {
            setPending(true);
            setError(null);
            try {
              await saveAccountGroup(editing === "new" ? null : editing.id, {
                name: String(data.get("name")).trim(),
                description: String(data.get("description") ?? ""),
                account_ids: data.getAll("account_ids").map(String),
              });
              setGroups(await listAccountGroups());
              setEditing(null);
            } catch (e) {
              setError(e instanceof Error ? e.message : "Could not save group");
            } finally {
              setPending(false);
            }
          }}
        >
          <h3>{editing === "new" ? "Create group" : `Edit ${editing.name}`}</h3>
          <label>
            Group name
            <input
              name="name"
              required
              maxLength={100}
              placeholder="e.g. Religious"
              defaultValue={editing === "new" ? "" : editing.name}
            />
          </label>
          <label>
            Description
            <input
              name="description"
              maxLength={500}
              defaultValue={editing === "new" ? "" : editing.description}
            />
          </label>
          <label>
            Find accounts
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name, username, or platform"
            />
          </label>
          <fieldset className="group-members">
            <legend>Member accounts</legend>
            {accounts.map((account) => (
              <label
                key={account.id}
                hidden={
                  !`${account.label} ${account.username} ${account.platform}`
                    .toLowerCase()
                    .includes(query.toLowerCase())
                }
              >
                <input
                  type="checkbox"
                  name="account_ids"
                  value={account.id}
                  defaultChecked={
                    editing !== "new" &&
                    editing.account_ids.includes(account.id)
                  }
                />
                <span>
                  <strong>{account.label}</strong>
                  <small>
                    {account.platform} · @{account.username} ·{" "}
                    {account.connection_status}
                  </small>
                </span>
              </label>
            ))}
            {!accounts.length && (
              <p>Connect an account above, then add it here.</p>
            )}
          </fieldset>
          <div className="inline-actions">
            <button disabled={pending}>
              {pending ? "Saving…" : "Save group"}
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() => setEditing(null)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

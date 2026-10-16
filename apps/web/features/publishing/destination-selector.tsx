"use client";
import { useState } from "react";
import type { SocialAccount, SocialAccountGroup } from "../../lib/contracts";

export function DestinationSelector({
  accounts,
  groups,
  selected,
  onChange,
}: {
  accounts: SocialAccount[];
  groups: SocialAccountGroup[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const [mode, setMode] = useState("accounts");
  const [query, setQuery] = useState("");
  const connected = accounts.filter(
    (a) => a.is_active && a.connection_status === "connected",
  );
  function choose(ids: string[]) {
    onChange(ids.filter((id) => connected.some((a) => a.id === id)));
  }
  return (
    <div className="distribution-selector">
      <div
        className="inline-actions"
        role="group"
        aria-label="Choose destination by"
      >
        {["accounts", "platform", "group"].map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={mode === value}
            onClick={() => setMode(value)}
          >
            {value === "group"
              ? "Social group"
              : value === "platform"
                ? "Platform"
                : "Accounts"}
          </button>
        ))}
      </div>
      {mode === "group" && (
        <label>
          Social group
          <select
            aria-label="Social group"
            defaultValue=""
            onChange={(e) =>
              choose(
                groups.find((g) => g.id === e.target.value)?.account_ids ?? [],
              )
            }
          >
            <option value="">Choose a group…</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name} (
                {
                  g.account_ids.filter((id) =>
                    connected.some((a) => a.id === id),
                  ).length
                }{" "}
                connected)
              </option>
            ))}
          </select>
          <small>
            Disconnected members are excluded. Check the destinations below
            before publishing.
          </small>
        </label>
      )}
      {mode === "platform" && (
        <label>
          Social platform
          <select
            defaultValue=""
            onChange={(e) =>
              choose(
                connected
                  .filter((a) => a.platform === e.target.value)
                  .map((a) => a.id),
              )
            }
          >
            <option value="">Choose a platform…</option>
            {[...new Set(accounts.map((a) => a.platform))].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        Find destinations
        <input
          placeholder="Search accounts"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      <div className="destination-checks">
        {accounts
          .filter((a) => a.is_active)
          .map((a) => (
            <label
              key={a.id}
              hidden={
                !`${a.label} ${a.username} ${a.platform}`
                  .toLowerCase()
                  .includes(query.toLowerCase())
              }
            >
              <input
                type="checkbox"
                checked={selected.includes(a.id)}
                disabled={a.connection_status !== "connected"}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...selected, a.id]
                      : selected.filter((id) => id !== a.id),
                  )
                }
              />
              <span>
                <strong>{a.label}</strong>
                <small>
                  {a.platform} · @{a.username} · {a.connection_status}
                </small>
              </span>
            </label>
          ))}
      </div>
      <p className="destination-summary" aria-live="polite">
        {selected.length} selected:{" "}
        {accounts
          .filter((a) => selected.includes(a.id))
          .map((a) => `${a.label} (${a.platform})`)
          .join(", ") || "Choose a destination"}
      </p>
    </div>
  );
}

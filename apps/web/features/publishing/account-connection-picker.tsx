"use client";

import { useEffect, useState } from "react";

import type { SocialAccount } from "../../lib/contracts";
import { getOAuthAccountSelection, selectOAuthAccount } from "./api";

type Selection = Awaited<ReturnType<typeof getOAuthAccountSelection>>;

export function AccountConnectionPicker({
  onConnected,
}: {
  onConnected: (account: SocialAccount) => Promise<void>;
}) {
  const [pending, setPending] = useState<{
    token: string;
    selection: Selection;
  } | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get(
      "connection_selection",
    );
    if (!token) return;
    let active = true;
    void getOAuthAccountSelection(token)
      .then((selection) => {
        if (active) setPending({ token, selection });
      })
      .catch((caught: Error) => {
        if (active) setError(caught.message);
      });
    return () => {
      active = false;
    };
  }, []);

  async function connect() {
    if (!pending || !selected) return;
    setBusy(true);
    setError(null);
    try {
      const account = await selectOAuthAccount(pending.token, selected);
      // A selection is consumed once. Remove it before refreshing account data.
      const url = new URL(window.location.href);
      url.searchParams.delete("connection_selection");
      window.history.replaceState(null, "", url.toString());
      setPending(null);
      await onConnected(account);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not connect account",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!pending)
    return error ? (
      <p className="error" role="alert">
        {error}
      </p>
    ) : null;
  return (
    <section
      className="account-selection-panel"
      aria-labelledby="choose-account-title"
    >
      <span className="eyebrow">FINISH CONNECTING</span>
      <h2 id="choose-account-title">Choose the destination to connect</h2>
      <p>
        Your Facebook login returned these{" "}
        {pending.selection.platform === "instagram"
          ? "Instagram accounts"
          : "Pages"}
        . Select the destination you want to connect. If a destination is
        missing, check its access in Meta and make sure the Instagram account is
        linked to the correct Facebook Page.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p>
        When adding Pages in Facebook Login, keep access to your existing
        destinations selected as well.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void connect();
        }}
      >
        <fieldset disabled={busy}>
          <legend>
            {pending.selection.platform === "instagram"
              ? "Instagram account"
              : "Facebook Page"}
          </legend>
          {pending.selection.candidates.map((candidate) => (
            <label
              key={candidate.external_account_id}
              className={`account-selection-choice ${selected === candidate.external_account_id ? "selected" : ""}`}
            >
              <input
                type="radio"
                name="destination"
                required
                value={candidate.external_account_id}
                checked={selected === candidate.external_account_id}
                onChange={() => setSelected(candidate.external_account_id)}
              />
              <span>
                <strong>{candidate.display_name}</strong>
                {candidate.username && <span>@{candidate.username}</span>}
                {candidate.parent_page_name && (
                  <small>Facebook Page: {candidate.parent_page_name}</small>
                )}
                <small>Account ID: {candidate.external_account_id}</small>
                {candidate.already_connected && (
                  <small>Already connected · refresh this connection</small>
                )}
              </span>
            </label>
          ))}
        </fieldset>
        <button
          type="submit"
          className="primary-button"
          disabled={!selected || busy}
        >
          {busy ? "Connecting…" : "Connect selected destination"}
        </button>
      </form>
    </section>
  );
}

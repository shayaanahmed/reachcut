"use client";

import { useEffect, useState } from "react";
import { listSocialAccounts } from "../publishing/api";
import type { SocialAccount } from "../../lib/contracts";
import { defaults, request } from "./api";
import type { Preset, Providers } from "./api";
import { matchesVoiceModel } from "./voice-models";

export function NarrationSettings() {
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  useEffect(() => {
    void listSocialAccounts()
      .then(setAccounts)
      .catch(() => {});
  }, []);
  const [providers, setProviders] = useState<Providers | null>(null);
  const [config, setConfig] = useState(defaults);
  const [name, setName] = useState("My channel");
  const [presetId, setPresetId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pronunciations, setPronunciations] = useState("{}");
  useEffect(() => {
    void Promise.all([
      request<Providers>("/shorts/providers"),
      request<Preset[]>("/channel-presets"),
    ])
      .then(([state, presets]) => {
        setProviders(state);
        if (presets[0]) {
          setConfig(presets[0].settings);
          setName(presets[0].name);
          setPresetId(presets[0].id);
          setPronunciations(JSON.stringify(presets[0].settings.pronunciations));
        }
      })
      .catch((e: Error) => setError(e.message));
  }, []);
  const engine = providers?.narration.engines.find((e) =>
    matchesVoiceModel(e, config),
  );
  return (
    <section className="settings-card">
      <h2>Narration and channel presets</h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <p>
        Voicebox:{" "}
        {providers?.narration.connected ? "connected" : "offline or checking"}.{" "}
        {providers?.narration.error}
      </p>
      <p>
        Urdu and Urdu-English narration are unverified in Voicebox. Use uploaded
        narration. Models must be explicitly installed in Voicebox; ReachCut
        does not download them.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError("");
          void (async () => {
            try {
              const saved = await request<Preset>(
                presetId ? `/channel-presets/${presetId}` : "/channel-presets",
                presetId ? "PUT" : "POST",
                {
                  name,
                  settings: {
                    ...config,
                    pronunciations: JSON.parse(pronunciations),
                  },
                },
              );
              setPresetId(saved.id);
              setNotice("Channel preset saved");
            } catch (e) {
              setError(
                e instanceof Error ? e.message : "Could not save preset",
              );
            }
          })();
        }}
      >
        <label>
          Preset name
          <input
            value={name}
            required
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Audience
          <input
            value={config.audience}
            onChange={(e) => setConfig({ ...config, audience: e.target.value })}
          />
        </label>
        <label>
          Tone
          <input
            value={config.tone}
            onChange={(e) => setConfig({ ...config, tone: e.target.value })}
          />
        </label>
        <label>
          Default language
          <select
            value={config.language}
            onChange={(e) => setConfig({ ...config, language: e.target.value })}
          >
            <option value="en">English</option>
            <option value="ur">Urdu (uploaded)</option>
            <option value="ur-en">Urdu-English (uploaded)</option>
          </select>
        </label>
        <label>
          Default voice
          <select
            value={config.profile_id}
            onChange={(e) =>
              setConfig({ ...config, profile_id: e.target.value })
            }
          >
            <option value="">Upload narration</option>
            {providers?.narration.profiles.map((p) => (
              <option value={p.id} key={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Engine and model
          <select
            value={engine?.model_name ?? ""}
            onChange={(e) => {
              const selected = providers?.narration.engines.find(
                (item) => item.model_name === e.target.value,
              );
              if (selected)
                setConfig({
                  ...config,
                  engine: selected.engine,
                  model_size: selected.model_name.includes("0.6B")
                    ? "0.6B"
                    : selected.model_name.includes("3b")
                      ? "3B"
                      : selected.engine === "tada"
                        ? "1B"
                        : "1.7B",
                  delivery: "",
                });
            }}
          >
            <option value="">Select an installed model</option>
            {providers?.narration.engines.map((item) => (
              <option
                key={item.model_name}
                value={item.model_name}
                disabled={!item.downloaded}
              >
                {item.display_name} ·{" "}
                {item.downloaded
                  ? item.languages.join(", ")
                  : "install in Voicebox"}
              </option>
            ))}
          </select>
        </label>
        {engine?.supports_delivery && (
          <label>
            Delivery instructions
            <input
              value={config.delivery}
              onChange={(e) =>
                setConfig({ ...config, delivery: e.target.value })
              }
            />
          </label>
        )}
        <label>
          Pronunciation corrections (JSON term to pronunciation)
          <textarea
            value={pronunciations}
            onChange={(e) => setPronunciations(e.target.value)}
          />
        </label>
        <label>
          Caption font
          <input
            value={config.caption_font}
            onChange={(e) =>
              setConfig({ ...config, caption_font: e.target.value })
            }
          />
        </label>
        <label>
          Default publishing destinations
          <select
            multiple
            value={config.destinations}
            onChange={(e) =>
              setConfig({
                ...config,
                destinations: Array.from(
                  e.target.selectedOptions,
                  (option) => option.value,
                ),
              })
            }
          >
            {accounts
              .filter((account) => account.is_active)
              .map((account) => (
                <option key={account.id} value={account.id}>
                  {account.label} · {account.platform}
                </option>
              ))}
          </select>
        </label>
        <button>Save channel preset</button>
      </form>
      <details>
        <summary>Provider capabilities and budgets</summary>
        <p>
          Research hosts: {providers?.research.allowed_hosts.join(", ")}.{" "}
          {providers?.research.limitation}
        </p>
        <p>
          Local Ollama scripting, Voicebox narration, uploaded images and
          recordings, and explanation cards. Only local, free production
          providers are registered. Time estimates are unavailable. Narration
          attempts are bounded to {config.max_attempts} per section.
        </p>
      </details>
    </section>
  );
}

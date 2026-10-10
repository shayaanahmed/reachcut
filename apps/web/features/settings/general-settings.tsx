"use client";

import { useEffect, useState } from "react";

import type { RuntimeSettings } from "../../lib/contracts";
import {
  getRuntimeSettings,
  listOllamaModels,
  saveRuntimeSettings,
} from "./api";

export function GeneralSettings() {
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getRuntimeSettings()
      .then(setSettings)
      .catch((caught: Error) => setError(caught.message));
  }, []);

  useEffect(() => {
    const baseUrl = settings?.ollama_base_url.trim();
    if (!baseUrl) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setLoadingModels(true);
      setModelError(null);
      void listOllamaModels(baseUrl)
        .then((available) => {
          if (!active) return;
          setModels(available);
          setSettings((current) => {
            if (!current || current.ollama_base_url.trim() !== baseUrl)
              return current;
            if (
              available.length > 0 &&
              !available.includes(current.editorial_model)
            )
              return { ...current, editorial_model: available[0] };
            return current;
          });
        })
        .catch((caught: Error) => {
          if (!active) return;
          setModels([]);
          setModelError(caught.message);
        })
        .finally(() => {
          if (active) setLoadingModels(false);
        });
    }, 450);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [settings?.ollama_base_url, refreshKey]);

  if (!settings)
    return (
      <main className="page">
        <div className="loading-card">Loading configuration…</div>
      </main>
    );

  return (
    <main className="page settings-page">
      <div className="topbar">
        <div>
          <span className="eyebrow">LOCAL AI</span>
          <h1>ReachCut settings</h1>
          <p>Choose the Ollama server and model used for clip selection.</p>
        </div>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      <form
        className="settings-card"
        onSubmit={(event) => {
          event.preventDefault();
          setSaving(true);
          setError(null);
          void saveRuntimeSettings(settings)
            .then((saved) => {
              setSettings(saved);
              setMessage("Settings saved. New analyses will use this model.");
            })
            .catch((caught: Error) => setError(caught.message))
            .finally(() => setSaving(false));
        }}
      >
        <div className="settings-card-heading">
          <div>
            <span className="eyebrow">EDITORIAL ENGINE</span>
            <h2>Ollama connection</h2>
          </div>
          <span className="local-badge">Runs locally</span>
        </div>
        <label>
          Ollama URL
          <input
            type="url"
            required
            value={settings.ollama_base_url}
            onChange={(event) =>
              setSettings({ ...settings, ollama_base_url: event.target.value })
            }
            placeholder="http://127.0.0.1:11434"
          />
          <small>
            Use the mini-PC LAN address when Ollama runs on another machine.
          </small>
        </label>
        <label>
          LLM model
          <select
            required
            value={settings.editorial_model}
            onChange={(event) =>
              setSettings({ ...settings, editorial_model: event.target.value })
            }
            disabled={loadingModels || models.length === 0}
          >
            {loadingModels && <option value="">Loading models…</option>}
            {!loadingModels && models.length === 0 && (
              <option value={settings.editorial_model}>
                {modelError ? "Ollama is unavailable" : "No models installed"}
              </option>
            )}
            {models.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
          <small aria-live="polite">
            {loadingModels
              ? "Reading installed models from this Ollama server…"
              : modelError
                ? modelError
                : `${models.length} installed model${models.length === 1 ? "" : "s"} available.`}
          </small>
        </label>
        <div className="settings-actions">
          <button
            type="button"
            className="secondary"
            disabled={loadingModels || saving}
            onClick={() => setRefreshKey((current) => current + 1)}
          >
            {loadingModels ? "Refreshing…" : "Refresh models"}
          </button>
          <button
            className="primary-button"
            disabled={saving || loadingModels || models.length === 0}
          >
            {saving ? "Saving…" : "Save settings"}
          </button>
        </div>
      </form>
    </main>
  );
}

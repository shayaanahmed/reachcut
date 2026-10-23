"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { RuntimeSettings } from "../../lib/contracts";
import {
  getRuntimeSettings,
  listOllamaModels,
  saveRuntimeSettings,
} from "./api";

const MODEL_ROLES = [
  {
    key: "clip_selection",
    label: "Clip selection & editorial",
    hint: "Suggested: qwen3:14b; compare qwen3:32b when memory permits.",
  },
  {
    key: "research",
    label: "Source analysis & ideas",
    hint: "Suggested: qwen3:14b for synthesizing sources. The model does not measure search demand.",
  },
  {
    key: "scripting",
    label: "Scripts & storyboards",
    hint: "Suggested: qwen3:14b; compare qwen3:32b for longer planning and revisions.",
  },
  {
    key: "growth",
    label: "Audience, SEO & performance learning",
    hint: "Suggested: qwen3:14b for audience inference, openings and publishing copy.",
  },
  {
    key: "metadata",
    label: "Titles, captions & hashtags",
    hint: "Suggested: qwen3:8b for responsive structured writing.",
  },
  {
    key: "translation",
    label: "Caption translation",
    hint: "Suggested: qwen3:8b; compare qwen3:14b using your actual languages.",
  },
  {
    key: "visual_review",
    label: "Artwork & final video review",
    hint: "Suggested: qwen3-vl:8b. Requires image input support.",
  },
  {
    key: "image_generation",
    label: "Illustration generation",
    hint: "Suggested: x/flux2-klein:4b when installed. Requires image generation capability on a supported Ollama macOS host.",
  },
] as const;

export function applyModelPreset(
  settings: RuntimeSettings,
  installed: string[],
  preset: "Fast" | "Balanced" | "Quality",
): RuntimeSettings {
  const find = (names: string[]) =>
    names
      .map((name) =>
        installed.find(
          (model) => model === name || model.startsWith(name + "-"),
        ),
      )
      .find(Boolean);
  const text = find(
    preset === "Quality"
      ? ["qwen3:32b", "qwen3:14b", "qwen3:8b"]
      : preset === "Fast"
        ? ["qwen3:8b", "qwen3:4b"]
        : ["qwen3:14b", "qwen3:8b"],
  );
  const light = find(["qwen3:8b", "qwen3:4b"]) ?? text;
  const vision = find(["qwen3-vl:8b", "qwen3-vl:4b", "gemma3:12b"]);
  return {
    ...settings,
    task_models: {
      ...settings.task_models,
      ...Object.fromEntries(
        MODEL_ROLES.flatMap((role) => {
          if (role.key === "image_generation") return [];
          const model =
            role.key === "visual_review"
              ? vision
              : ["metadata", "translation"].includes(role.key)
                ? light
                : text;
          return model ? [[role.key, model]] : [];
        }),
      ),
    },
  };
}

export function GeneralSettings({ children }: { children?: ReactNode }) {
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelError, setModelError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getRuntimeSettings()
      .then(setSettings)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    const baseUrl = settings?.ollama_base_url.trim();
    if (!baseUrl) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setLoadingModels(true);
      setModelError(null);
      listOllamaModels(baseUrl)
        .then((available) => {
          if (active) setModels(available);
        })
        .catch((e) => {
          if (active) {
            setModels([]);
            setModelError(e.message);
          }
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
        <div className="loading-card">
          {error ? <p role="alert">{error}</p> : "Loading configuration…"}
        </div>
      </main>
    );

  function choices(current: string, allowDefault = false, vision = false) {
    return (
      <>
        {allowDefault && (
          <option value="">
            Use {vision ? "thumbnail vision" : "main LLM"} model
          </option>
        )}
        {current && !models.includes(current) && (
          <option value={current}>{current} (not installed)</option>
        )}
        {models.map((model) => (
          <option key={model} value={model}>
            {model}
          </option>
        ))}
      </>
    );
  }
  return (
    <main className="page settings-page">
      <header className="topbar">
        <div>
          <span className="eyebrow">LOCAL AI</span>
          <h1>ReachCut settings</h1>
          <p>
            Let AI prepare clips automatically and choose a model for each task.
          </p>
        </div>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <form
        className="settings-card"
        onSubmit={(event) => {
          event.preventDefault();
          setSaving(true);
          setError(null);
          setMessage(null);
          saveRuntimeSettings(settings)
            .then((saved) => {
              setSettings(saved);
              setMessage(
                "Settings saved. New AI tasks will use these choices.",
              );
            })
            .catch((e) => setError(e.message))
            .finally(() => setSaving(false));
        }}
      >
        <h2>Ollama connection</h2>
        <label>
          Ollama URL
          <input
            type="url"
            required
            value={settings.ollama_base_url}
            onChange={(event) =>
              setSettings({ ...settings, ollama_base_url: event.target.value })
            }
          />
          <small>
            Use the LAN address when Ollama runs on another machine.
          </small>
        </label>
        <label>
          LLM model
          <select
            required
            value={settings.editorial_model}
            disabled={loadingModels || !models.length}
            onChange={(event) =>
              setSettings({ ...settings, editorial_model: event.target.value })
            }
          >
            {choices(settings.editorial_model)}
          </select>
          <small aria-live="polite">
            {loadingModels
              ? "Reading installed models…"
              : (modelError ??
                `${models.length} installed model${models.length === 1 ? "" : "s"} available.`)}
          </small>
        </label>
        <label>
          Thumbnail vision model
          <select
            required
            value={settings.thumbnail_model}
            disabled={loadingModels || !models.length}
            onChange={(event) =>
              setSettings({ ...settings, thumbnail_model: event.target.value })
            }
          >
            {choices(settings.thumbnail_model)}
          </select>
          <small>
            Suggested: qwen3-vl:8b. Reviews frames; ReachCut renders the design
            locally.
          </small>
        </label>
        <section aria-label="Automatic growth">
          <h2>Automatic growth</h2>
          <label className="automatic-growth-toggle">
            <input
              type="checkbox"
              checked={settings.automatic_growth ?? true}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  automatic_growth: event.target.checked,
                })
              }
            />
            Automatically optimize new clips
          </label>
          <p>
            AI fills the audience and search brief, learns from saved account
            results, chooses an opening, and prepares publishing copy.
            Unrendered clips receive an opening overlay and cover headline
            automatically. Finished exports keep their existing video.
          </p>
        </section>
        <section aria-label="Models by task">
          <h2>Models by task</h2>
          <p>
            Use a shared default or choose a model per task. ReachCut never
            downloads models automatically.
          </p>
          <div
            className="model-presets"
            role="group"
            aria-label="Model presets"
          >
            {(["Fast", "Balanced", "Quality"] as const).map((preset) => (
              <button
                key={preset}
                type="button"
                className="model-preset-card"
                aria-label={`Use ${preset.toLowerCase()} installed choices`}
                disabled={!models.length || saving}
                onClick={() =>
                  setSettings(applyModelPreset(settings, models, preset))
                }
              >
                <span className="preset-glyph" aria-hidden="true">
                  {preset === "Fast" ? "ϟ" : preset === "Balanced" ? "◈" : "✦"}
                </span>
                <strong>{preset}</strong>
                <small>
                  {preset === "Fast"
                    ? "Shorter waits · lighter models"
                    : preset === "Balanced"
                      ? "A practical everyday starting point"
                      : "Larger installed models for comparison"}
                </small>
              </button>
            ))}
          </div>
          <details className="advanced-models">
            <summary>Customize models by task</summary>
            {MODEL_ROLES.map((role) => (
              <label key={role.key}>
                {role.label}
                <select
                  value={settings.task_models?.[role.key] ?? ""}
                  disabled={loadingModels || !models.length}
                  onChange={(event) =>
                    setSettings({
                      ...settings,
                      task_models: {
                        ...settings.task_models,
                        [role.key]: event.target.value,
                      },
                    })
                  }
                >
                  {role.key === "image_generation" ? (
                    <>
                      <option value="">Use content series image model</option>
                      {choices(settings.task_models?.[role.key] ?? "")}
                    </>
                  ) : (
                    choices(
                      settings.task_models?.[role.key] ?? "",
                      true,
                      role.key === "visual_review",
                    )
                  )}
                </select>
                <small>{role.hint}</small>
              </label>
            ))}
          </details>
          <label>
            Speech transcription
            <select
              value={settings.transcription_model ?? "large-v3-turbo"}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  transcription_model: event.target.value,
                })
              }
            >
              {[
                "tiny",
                "base",
                "small",
                "medium",
                "large-v3",
                "large-v3-turbo",
              ].map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
            <small>
              large-v3-turbo is the balanced default. Compare large-v3 for
              accuracy, or small for faster processing. Models must already be
              cached locally.
            </small>
          </label>
          <p>
            These are starting recommendations for this workflow, not benchmarks
            on your hardware. Larger models need more memory and can take
            longer. Image generation uses the content series choice unless
            overridden here; voice models are in Narration settings below.
          </p>
          <p>
            <a
              href="https://ollama.com/library/qwen3"
              target="_blank"
              rel="noreferrer"
            >
              Qwen3 models ↗
            </a>{" "}
            ·{" "}
            <a
              href="https://ollama.com/library/qwen3-vl"
              target="_blank"
              rel="noreferrer"
            >
              Qwen3 vision models ↗
            </a>{" "}
            ·{" "}
            <a
              href="https://github.com/SYSTRAN/faster-whisper"
              target="_blank"
              rel="noreferrer"
            >
              Whisper runtime ↗
            </a>
          </p>
        </section>
        <div className="settings-actions">
          <button
            type="button"
            disabled={loadingModels || saving}
            onClick={() => setRefreshKey((value) => value + 1)}
          >
            {loadingModels ? "Refreshing…" : "Refresh models"}
          </button>
          <button disabled={saving || loadingModels}>
            {saving ? "Saving…" : "Save settings"}
          </button>
        </div>
      </form>
      {children}
    </main>
  );
}

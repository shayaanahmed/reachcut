"use client";

import { useCallback, useEffect, useState } from "react";

import type { SetupStatus } from "../../lib/contracts";
import { downloadEditorialModel, getSetupStatus } from "./api";

type SetupAssistantProps = {
  initialStatus?: SetupStatus;
  onReady?: (status: SetupStatus) => void;
};

function formatBytes(bytes: number | null): string | null {
  if (bytes === null) return null;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export function SetupAssistant({
  initialStatus,
  onReady,
}: SetupAssistantProps) {
  const [status, setStatus] = useState<SetupStatus | null>(
    initialStatus ?? null,
  );
  const [checking, setChecking] = useState(!initialStatus);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setChecking(true);
    setError(null);
    try {
      setStatus(await getSetupStatus());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Setup check failed");
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    if (initialStatus) return;
    let active = true;
    void getSetupStatus()
      .then((result) => {
        if (active) setStatus(result);
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(
            cause instanceof Error ? cause.message : "Setup check failed",
          );
        }
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [initialStatus]);

  async function installModel() {
    setDownloading(true);
    setError(null);
    try {
      setStatus(await downloadEditorialModel());
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Model download failed",
      );
    } finally {
      setDownloading(false);
    }
  }

  const toolsReady = Boolean(status?.ffmpeg && status.ffprobe);
  const modelSize = formatBytes(status?.editorial_model_size_bytes ?? null);

  return (
    <main className="narrow-page setup-page">
      <header className="setup-hero">
        <span className="eyebrow">FIRST-RUN SETUP</span>
        <h1>
          {status?.ready
            ? "Your local studio is ready"
            : "Finish local AI setup"}
        </h1>
        <p>
          ReachCut keeps processing on this computer. The app is installed; now
          connect its local AI runtime and model.
        </p>
      </header>

      {error && (
        <p className="error setup-error" role="alert">
          {error}
        </p>
      )}

      <section className="setup-checklist" aria-label="Setup checklist">
        <article className={status?.ollama_available ? "complete" : "action"}>
          <span className="setup-step">1</span>
          <div>
            <small>LOCAL AI RUNTIME</small>
            <h2>Ollama</h2>
            <p>
              {checking
                ? "Checking this computer…"
                : status?.ollama_available
                  ? `Running locally${status.ollama_version ? ` · version ${status.ollama_version}` : ""}.`
                  : "Install Ollama, open it once, then return here."}
            </p>
          </div>
          <div className="setup-action">
            {status?.ollama_available ? (
              <strong>✓ Connected</strong>
            ) : (
              <a
                className="primary-link"
                href={
                  status?.ollama_install_url ?? "https://ollama.com/download"
                }
                target="_blank"
                rel="noreferrer"
              >
                Download Ollama ↗
              </a>
            )}
          </div>
        </article>

        <article
          className={status?.editorial_model_installed ? "complete" : "action"}
        >
          <span className="setup-step">2</span>
          <div>
            <small>EDITORIAL MODEL</small>
            <h2>{status?.editorial_model ?? "Qwen"}</h2>
            <p>
              {status?.editorial_model_installed
                ? `Available locally${modelSize ? ` · ${modelSize}` : ""}.`
                : "Download once for highlight selection, hooks, titles, and editorial reasoning. Ollama can resume an interrupted pull."}
            </p>
          </div>
          <div className="setup-action">
            {status?.editorial_model_installed ? (
              <strong>✓ Installed</strong>
            ) : (
              <button
                className="primary-button"
                type="button"
                disabled={!status?.ollama_available || downloading}
                onClick={() => void installModel()}
              >
                {downloading ? "Downloading…" : "Download model"}
              </button>
            )}
          </div>
        </article>

        <article className="informational">
          <span className="setup-step">3</span>
          <div>
            <small>TRANSCRIPTION MODEL</small>
            <h2>{status?.whisper_model ?? "Whisper"}</h2>
            <p>
              Downloads and caches automatically the first time you analyze a
              video. That first analysis needs internet and takes longer.
            </p>
          </div>
          <div className="setup-action">
            <strong>Automatic</strong>
          </div>
        </article>

        {!toolsReady && status && (
          <article className="warning">
            <span className="setup-step">!</span>
            <div>
              <small>APPLICATION TOOLS</small>
              <h2>Repair ReachCut</h2>
              <p>
                The bundled {status.ffmpeg ? "ffprobe" : "FFmpeg"} tool is
                missing. Reinstall this ReachCut build before processing media.
              </p>
            </div>
          </article>
        )}
      </section>

      <footer className="setup-footer">
        <p>Models stay in your ReachCut data directory and are not uploaded.</p>
        <div>
          <button
            className="secondary-button"
            type="button"
            disabled={checking || downloading}
            onClick={() => void refresh()}
          >
            {checking ? "Checking…" : "Check again"}
          </button>
          {status?.ready && onReady && (
            <button
              className="primary-button"
              type="button"
              onClick={() => onReady(status)}
            >
              Open dashboard →
            </button>
          )}
        </div>
      </footer>
    </main>
  );
}

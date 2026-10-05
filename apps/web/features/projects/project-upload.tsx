"use client";

import { useEffect, useRef, useState } from "react";

import type { Project } from "../../lib/contracts";
import type { UrlImportRequest } from "./api";

type ImportMode = "file" | "url";
type ImportState = "idle" | "working" | "ready" | "failed";

const URL_STEPS = [
  { title: "Check the link", detail: "Validate the source and permissions" },
  {
    title: "Fetch the video",
    detail: "Download one playable source with yt-dlp",
  },
  {
    title: "Prepare the project",
    detail: "Verify the file and save it locally",
  },
  {
    title: "Open your workspace",
    detail: "Ready for transcription and highlights",
  },
] as const;

export function ProjectUpload({
  busy,
  onUpload,
  onImportUrl,
  onCreated,
  error,
}: {
  busy: boolean;
  onUpload: (data: FormData) => Promise<Project | undefined>;
  onImportUrl: (request: UrlImportRequest) => Promise<Project | undefined>;
  onCreated: (project: Project) => void;
  error?: string | null;
}) {
  const [mode, setMode] = useState<ImportMode>("file");
  const [url, setUrl] = useState("");
  const [importState, setImportState] = useState<ImportState>("idle");
  const [activeStep, setActiveStep] = useState(0);
  const stepTimer = useRef<number | null>(null);
  const navigationTimer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (stepTimer.current !== null) window.clearInterval(stepTimer.current);
      if (navigationTimer.current !== null)
        window.clearTimeout(navigationTimer.current);
    },
    [],
  );

  async function importUrl(data: FormData) {
    setImportState("working");
    setActiveStep(0);
    stepTimer.current = window.setInterval(
      () => setActiveStep((current) => Math.min(current + 1, 2)),
      2200,
    );
    const created = await onImportUrl({
      title: String(data.get("title")),
      url: String(data.get("url")),
      authorization_confirmed: data.get("authorization_confirmed") === "true",
    });
    if (stepTimer.current !== null) window.clearInterval(stepTimer.current);
    stepTimer.current = null;
    if (!created) {
      setImportState("failed");
      return;
    }
    setActiveStep(3);
    setImportState("ready");
    navigationTimer.current = window.setTimeout(() => onCreated(created), 700);
  }

  return (
    <section className="import-panel" aria-labelledby="new-project">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">SOURCE MEDIA</span>
          <h2 id="new-project">Start a new project</h2>
        </div>
        <div className="source-tabs" role="tablist" aria-label="Source type">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "file"}
            className={mode === "file" ? "active" : ""}
            disabled={busy}
            onClick={() => setMode("file")}
          >
            Upload file
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "url"}
            className={mode === "url" ? "active" : ""}
            disabled={busy}
            onClick={() => setMode("url")}
          >
            Import URL
          </button>
        </div>
      </div>

      {mode === "file" ? (
        <form
          className="import-form"
          action={async (data) => {
            const created = await onUpload(data);
            if (created) onCreated(created);
          }}
        >
          <label>
            Project name
            <input
              name="title"
              required
              maxLength={200}
              placeholder="Founder interview — August"
            />
          </label>
          <label className="file-drop">
            Source video
            <input name="media" type="file" accept="video/*,.mkv" required />
            <span>Choose a video from your computer</span>
            <small>
              MP4, MOV, MKV, WebM · up to the configured upload limit
            </small>
          </label>
          <Authorization disabled={busy} />
          <button className="primary-button" disabled={busy}>
            {busy ? "Importing…" : "Create project"}
          </button>
        </form>
      ) : (
        <div className="url-import-layout">
          <form
            className="url-import-form"
            onSubmit={(event) => {
              event.preventDefault();
              void importUrl(new FormData(event.currentTarget));
            }}
          >
            <div className="field-group">
              <label htmlFor="source-url">Public video URL</label>
              <div className="url-field">
                <span aria-hidden="true">↗</span>
                <input
                  id="source-url"
                  name="url"
                  type="url"
                  inputMode="url"
                  required
                  disabled={busy}
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="Paste a YouTube, TikTok, Vimeo, or other public video link"
                />
              </div>
              <div
                className="supported-platforms"
                aria-label="Common supported sources"
              >
                <span>YouTube</span>
                <span>TikTok</span>
                <span>Vimeo</span>
                <span>Instagram</span>
                <span>Twitch</span>
                <span>Facebook</span>
                <span>X</span>
              </div>
            </div>
            {url && (
              <div className="source-preview">
                <span className="source-preview-mark" aria-hidden="true">
                  ▶
                </span>
                <span>
                  <strong>{sourceLabel(url)}</strong>
                  <small>{safeHostname(url)}</small>
                </span>
                <span className="source-check">Link added</span>
              </div>
            )}
            <label>
              Project name
              <input
                name="title"
                required
                disabled={busy}
                maxLength={200}
                placeholder="Product launch cutdowns"
              />
            </label>
            <Authorization disabled={busy} />
            <button className="primary-button import-action" disabled={busy}>
              {importState === "working"
                ? "Importing video…"
                : importState === "failed"
                  ? "Try import again"
                  : "Continue with this video"}
              <span aria-hidden="true">→</span>
            </button>
            <div className="trust-row" aria-label="Import safeguards">
              <span>✓ One video only</span>
              <span>✓ Stored locally</span>
              <span>✓ No auto-publish</span>
            </div>
          </form>

          <ImportJourney
            state={importState}
            activeStep={activeStep}
            error={error}
          />
        </div>
      )}
      <p className="notice">
        URL import supports approved public media hosts through the local yt-dlp
        runtime. A public link does not grant publication rights.
      </p>
    </section>
  );
}

function ImportJourney({
  state,
  activeStep,
  error,
}: {
  state: ImportState;
  activeStep: number;
  error?: string | null;
}) {
  const progress =
    state === "idle"
      ? 0
      : state === "ready"
        ? 100
        : Math.round(((activeStep + 0.55) / URL_STEPS.length) * 100);
  return (
    <aside className={`import-journey ${state}`} aria-live="polite">
      <div className="journey-heading">
        <span className="eyebrow">WHAT HAPPENS NEXT</span>
        <strong>
          {state === "ready"
            ? "Video imported"
            : state === "failed"
              ? "Import needs attention"
              : state === "working"
                ? "Bringing in your video"
                : "A guided local import"}
        </strong>
        <p>
          {state === "failed"
            ? error ||
              "The source could not be imported. Check the link and try again."
            : "Keep this page open while Clipper prepares your source."}
        </p>
      </div>
      <div className="journey-progress" aria-hidden="true">
        <span style={{ width: `${progress}%` }} />
      </div>
      <ol>
        {URL_STEPS.map((step, index) => {
          const completed =
            state === "ready" || (state === "working" && index < activeStep);
          const active = state === "working" && index === activeStep;
          const failed = state === "failed" && index === activeStep;
          return (
            <li
              className={
                completed
                  ? "completed"
                  : active
                    ? "active"
                    : failed
                      ? "failed"
                      : ""
              }
              key={step.title}
            >
              <span className="journey-step" aria-hidden="true">
                {completed ? "✓" : failed ? "!" : index + 1}
              </span>
              <span>
                <strong>{step.title}</strong>
                <small>{step.detail}</small>
              </span>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

function Authorization({ disabled }: { disabled: boolean }) {
  return (
    <label className="check">
      <input
        name="authorization_confirmed"
        type="checkbox"
        value="true"
        required
        disabled={disabled}
      />
      <span>I own, license, or have permission to repurpose this media.</span>
    </label>
  );
}

function safeHostname(value: string): string {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return "Waiting for a complete URL";
  }
}

function sourceLabel(value: string): string {
  const host = safeHostname(value);
  if (host.includes("youtube") || host === "youtu.be") return "YouTube video";
  if (host.includes("vimeo")) return "Vimeo video";
  if (host.includes("tiktok")) return "TikTok video";
  if (host.includes("instagram")) return "Instagram video";
  if (host.includes("twitch")) return "Twitch video";
  if (host.includes("facebook") || host === "fb.watch") return "Facebook video";
  if (host === "x.com" || host.includes("twitter")) return "X video";
  return "Public video source";
}

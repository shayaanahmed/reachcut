"use client";

import { useState } from "react";

import type { Project } from "../../lib/contracts";
import { ImportLanguage } from "../projects/import-language";
import { importProjectUrl, uploadProject } from "../projects/api";

export function ProjectSource({
  projects,
  selectedId,
  onSelect,
  onCreated,
}: {
  projects: Project[];
  selectedId: string;
  onSelect: (id: string) => void;
  onCreated: (project: Project) => void;
}) {
  const [mode, setMode] = useState<"existing" | "url" | "upload">("existing");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function create(data: FormData) {
    setBusy(true);
    setError(null);
    setNotice(null);
    setProgress(0);
    try {
      const project =
        mode === "url"
          ? await importProjectUrl({
              title: title.trim(),
              url,
              authorization_confirmed: true,
              ...(data.get("language")
                ? { language: String(data.get("language")) }
                : {}),
            })
          : await uploadProject(data, setProgress);
      onCreated(project);
      setNotice(
        `“${project.title}” added to the processing queue. You can continue setting up this automation.`,
      );
      setMode("existing");
      setTitle("");
      setUrl("");
      setFile(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not add source video",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="automation-source">
      <div className="source-tabs" role="group" aria-label="Source video input">
        {(["existing", "url", "upload"] as const).map((option) => (
          <button
            key={option}
            type="button"
            disabled={busy}
            aria-pressed={mode === option}
            className={mode === option ? "active" : ""}
            onClick={() => {
              setMode(option);
              setError(null);
            }}
          >
            {option === "existing"
              ? "Existing source video"
              : option === "url"
                ? "From URL"
                : "Upload video"}
          </button>
        ))}
      </div>
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {mode === "existing" ? (
        <>
          <label>
            Source video
            <select
              value={selectedId}
              onChange={(event) => onSelect(event.target.value)}
            >
              <option value="">Select a source video</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.title} · {project.status}
                </option>
              ))}
            </select>
          </label>
          <p className="notice">
            Queued source videos are welcome. Publishing waits until analysis is
            complete and your scheduled time arrives.
          </p>
        </>
      ) : (
        <form
          className="automation-source-form"
          onSubmit={(event) => {
            event.preventDefault();
            void create(new FormData(event.currentTarget));
          }}
        >
          {mode === "url" ? (
            <label>
              Public video URL
              <input
                name="url"
                type="url"
                required
                disabled={busy}
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://www.youtube.com/watch?v=…"
              />
            </label>
          ) : (
            <label className="automation-upload">
              Source video
              <input
                name="media"
                aria-label="Source video file"
                type="file"
                accept="video/*,.mkv"
                required
                disabled={busy}
                onChange={(event) => {
                  const selected = event.target.files?.[0] ?? null;
                  setFile(selected);
                  if (selected && !title)
                    setTitle(
                      selected.name
                        .replace(/\.[^.]+$/, "")
                        .replaceAll(/[-_]+/g, " "),
                    );
                }}
              />
              <small>
                {file
                  ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB`
                  : "Choose an MP4, MOV, MKV or WebM video"}
              </small>
            </label>
          )}
          <label>
            Source video name
            <input
              name="title"
              required
              maxLength={200}
              disabled={busy}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Give this source a name"
            />
          </label>
          <ImportLanguage disabled={busy} />
          <label className="check">
            <input
              name="authorization_confirmed"
              type="checkbox"
              value="true"
              required
              disabled={busy}
            />
            <span>
              I own, license, or have permission to repurpose this media.
            </span>
          </label>
          {busy && mode === "upload" && (
            <div role="status">
              <progress
                max={100}
                value={progress}
                aria-label="Upload progress"
              />
              <small>
                {progress < 100
                  ? `Uploading ${progress}%`
                  : "Saving video and joining the queue…"}
              </small>
            </div>
          )}
          <button className="primary-button" disabled={busy}>
            {busy
              ? mode === "url"
                ? "Adding to queue…"
                : "Uploading…"
              : "Add source video to queue"}
          </button>
          <p className="notice">
            {mode === "url"
              ? "The video downloads and processes in the background. Add more sources whenever you like."
              : "After the file finishes uploading, analysis runs in the background."}
          </p>
        </form>
      )}
    </div>
  );
}

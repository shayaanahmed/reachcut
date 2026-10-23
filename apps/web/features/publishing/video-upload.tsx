"use client";

import { useState } from "react";
import Link from "next/link";
import type { Project } from "../../lib/contracts";

export function PublishingVideoUpload({
  busy,
  onUpload,
  onCreated,
  destination = "publishing",
}: {
  busy: boolean;
  onUpload: (data: FormData) => Promise<Project | undefined>;
  onCreated: (project: Project) => void;
  destination?: "publishing" | "studio";
}) {
  const [title, setTitle] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [titles, setTitles] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<
    Record<number, { project?: Project; error?: string; working?: boolean }>
  >({});
  const locked = busy || uploading;
  const batch = files.length > 1;
  const pendingCount = files.filter(
    (_, index) => !results[index]?.project,
  ).length;

  async function upload(data: FormData) {
    setUploading(true);
    try {
      if (!batch) {
        const created = await onUpload(data);
        if (created) onCreated(created);
        return;
      }
      for (const [index, file] of files.entries()) {
        if (results[index]?.project) continue;
        setResults((current) => ({ ...current, [index]: { working: true } }));
        const item = new FormData();
        data.forEach((value, key) => item.append(key, value));
        item.set("media", file);
        item.set("title", titles[index].trim());
        try {
          const project = await onUpload(item);
          setResults((current) => ({
            ...current,
            [index]: project
              ? { project }
              : { error: "Upload failed. Retry this video." },
          }));
        } catch (error) {
          setResults((current) => ({
            ...current,
            [index]: {
              error:
                error instanceof Error
                  ? error.message
                  : "Upload failed. Retry this video.",
            },
          }));
        }
      }
    } finally {
      setUploading(false);
    }
  }

  function fileTitle(file: File) {
    return file.name
      .replace(/\.[^.]+$/, "")
      .replaceAll(/[-_]+/g, " ")
      .slice(0, 200);
  }
  return (
    <section className="import-panel" aria-labelledby="publishing-upload-title">
      <h2 id="publishing-upload-title">
        {destination === "studio"
          ? "Upload videos to edit"
          : "Upload finished video"}
      </h2>
      <p>
        {destination === "studio" ? (
          "Upload one or more MP4 videos to trim, add a text watermark, and layer a voice-over. Choose any uploaded video to open in Studio."
        ) : (
          <>
            Upload one or more MP4 videos and continue to the same accounts,
            groups, and scheduling options. Your video is kept as uploaded, with
            no clipping or added captions.
          </>
        )}
      </p>
      <form
        className="import-form modern-import-form"
        onSubmit={async (event) => {
          event.preventDefault();
          await upload(new FormData(event.currentTarget));
        }}
      >
        <label>
          Finished video (MP4)
          <input
            name="media"
            type="file"
            multiple
            accept="video/mp4,.mp4"
            required
            disabled={locked}
            onChange={(event) => {
              const selected = Array.from(event.currentTarget.files ?? []);
              setFiles(selected);
              setTitles(selected.map(fileTitle));
              setResults({});
              if (selected.length === 1) setTitle(fileTitle(selected[0]));
            }}
          />
        </label>
        {!batch && (
          <label>
            Video title
            <input
              name="title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              required
              maxLength={200}
              disabled={locked}
            />
          </label>
        )}
        {batch && (
          <div className="batch-video-uploads" aria-live="polite">
            <p>
              {files.length} videos selected ·{" "}
              {Object.values(results).filter((result) => result.project).length}{" "}
              uploaded
            </p>
            {files.map((file, index) => {
              const result = results[index];
              const clip = result?.project?.clips[0];
              return (
                <div
                  className="batch-video-upload"
                  key={`${file.name}-${index}`}
                >
                  <label>
                    {file.name}
                    <input
                      aria-label={`Title for ${file.name}`}
                      name={`video-title-${index}`}
                      value={titles[index]}
                      required
                      maxLength={200}
                      disabled={locked || !!result?.project}
                      onChange={(event) =>
                        setTitles((current) =>
                          current.map((value, item) =>
                            item === index ? event.target.value : value,
                          ),
                        )
                      }
                    />
                  </label>
                  {result?.working && <span role="status">Uploading…</span>}
                  {result?.error && (
                    <span className="error">{result.error}</span>
                  )}
                  {result?.project && clip && (
                    <Link
                      href={`/projects/${result.project.id}/clips/${clip.id}${destination === "publishing" ? "/publish" : ""}`}
                    >
                      {destination === "studio"
                        ? "Edit in Studio →"
                        : "Open publishing →"}
                    </Link>
                  )}
                </div>
              );
            })}
          </div>
        )}
        <label className="check">
          <input
            name="authorization_confirmed"
            type="checkbox"
            value="true"
            required
            disabled={locked}
          />
          <span>I own, license, or have permission to publish this video.</span>
        </label>
        <button
          className="primary-button"
          disabled={
            locked ||
            (batch
              ? !pendingCount ||
                titles.some(
                  (value, index) => !results[index]?.project && !value.trim(),
                )
              : !title.trim())
          }
        >
          {locked
            ? batch
              ? "Uploading videos…"
              : "Uploading video…"
            : batch
              ? pendingCount
                ? `Upload ${pendingCount} video${pendingCount === 1 ? "" : "s"}`
                : "All videos uploaded"
              : destination === "studio"
                ? "Upload and open Studio"
                : "Upload and continue to publishing"}
        </button>
      </form>
    </section>
  );
}

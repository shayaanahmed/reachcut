"use client";

import { useEffect, useMemo, useState } from "react";

import {
  classifyReferenceTemplate,
  importReferenceTemplate,
  listReferenceTemplates,
  referenceVideoUrl,
  referencePosterUrl,
  uploadReferenceTemplate,
  type ReferenceSelection,
  type ReferenceTemplate,
} from "./template-library-api";

type Props = {
  selection: ReferenceSelection;
  onSelect: (selection: ReferenceSelection) => void;
  disabled?: boolean;
};

export function TemplateLibrary({
  selection,
  onSelect,
  disabled = false,
}: Props) {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<ReferenceTemplate[]>([]);
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(4);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyReady, setOnlyReady] = useState(false);

  useEffect(() => {
    void listReferenceTemplates()
      .then(setItems)
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () =>
      items.filter((item) => {
        const text =
          `${item.name} ${item.blueprint?.format ?? item.source_category ?? ""} ${item.blueprint?.tags.join(" ") ?? ""}`.toLowerCase();
        return (
          (!onlyReady || item.status === "ready") &&
          text.includes(query.toLowerCase())
        );
      }),
    [items, query, onlyReady],
  );
  const readyCount = items.filter((item) => item.status === "ready").length;

  function update(item: ReferenceTemplate) {
    setItems((current) => [
      item,
      ...current.filter((value) => value.id !== item.id),
    ]);
  }
  async function classify(id: string) {
    setBusy(id);
    setError(null);
    try {
      const item = await classifyReferenceTemplate(id);
      update(item);
      if (item.status === "failed") setError(item.error);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Classification failed",
      );
    } finally {
      setBusy(null);
    }
  }
  async function add(file?: File) {
    setBusy("import");
    setError(null);
    try {
      const item = file
        ? await uploadReferenceTemplate(file)
        : await importReferenceTemplate(url.trim());
      update(item);
      setUrl("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Import failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section
      className="reference-library"
      aria-label="Reference template library"
    >
      <div className="video-format-heading">
        <div>
          <h3>Video templates</h3>
          <p>
            Choose the format your story should follow. Preview a clip to see
            its camera, pacing, and visual direction.
          </p>
        </div>
        <span>{readyCount} ready to use</span>
      </div>
      <button
        type="button"
        className={`studio-auto ${selection === "none" || selection === "auto" ? "active" : ""}`}
        aria-pressed={selection === "none" || selection === "auto"}
        disabled={disabled || busy !== null}
        onClick={() => onSelect("none")}
      >
        ✦ Auto · AI chooses the best video format
      </button>
      <p className="generation-disclosure" role="status">
        {selection === "none" || selection === "auto"
          ? "No template selected. AI will classify your story and choose a format when you create the short."
          : `Selected format: ${items.find((item) => item.id === selection)?.name ?? "Video template"}. Your story will follow this template.`}
      </p>
      <div className="reference-library-tools">
        <label>
          Search clips
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setLimit(4);
            }}
            placeholder="Name, format or AI tag"
          />
        </label>
        <label className="reference-filter">
          <input
            type="checkbox"
            checked={onlyReady}
            onChange={(event) => {
              setOnlyReady(event.target.checked);
              setLimit(4);
            }}
          />
          Classified only
        </label>
      </div>
      <details className="studio-details">
        <summary>Add a video template · link or upload</summary>
        <p>
          Save a video, then analyze it to make its format available for new
          stories.
        </p>
        <div className="reference-library-tools">
          <label>
            Video URL
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="Paste a supported video URL"
            />
          </label>
          <button
            type="button"
            disabled={disabled || busy !== null || !url.trim()}
            onClick={() => void add()}
          >
            Add video
          </button>
          <label>
            Upload your own MP4
            <input
              type="file"
              accept="video/mp4"
              disabled={disabled || busy !== null}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void add(file);
                event.target.value = "";
              }}
            />
          </label>
        </div>
      </details>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {loading && <p role="status">Loading video formats…</p>}
      {!loading && !error && items.length === 0 && (
        <div className="empty-state compact">
          <h3>No video templates yet</h3>
          <p>
            Add a reference video above, or write your story and let AI choose a
            built-in format.
          </p>
        </div>
      )}
      {items.length > 0 && filtered.length === 0 && (
        <p>No matching templates. Try a different search.</p>
      )}
      <div className="reference-template-grid">
        {filtered.slice(0, limit).map((item) => (
          <article
            key={item.id}
            className={selection === item.id ? "selected" : ""}
          >
            <video
              src={referenceVideoUrl(item)}
              poster={referencePosterUrl(item)}
              controls
              muted
              playsInline
              preload="none"
              aria-label={`Preview ${item.name}`}
            />
            <strong>{item.name}</strong>
            <small>
              {item.blueprint
                ? `${item.blueprint.format} · ${item.blueprint.tags.join(" · ")}`
                : `${item.source_category ?? "Reference clip"} · Awaiting AI classification`}
            </small>
            {item.blueprint && (
              <details>
                <summary>Template direction</summary>
                <p>{item.blueprint.visual_style}</p>
                <p>{item.blueprint.camera}</p>
                <p>{item.blueprint.pacing}</p>
                <p>{item.blueprint.story_structure}</p>
              </details>
            )}
            {item.error && <small className="error">{item.error}</small>}
            <div className="reference-library-tools">
              <button
                type="button"
                disabled={disabled || busy !== null}
                onClick={() => void classify(item.id)}
              >
                {busy === item.id
                  ? "Analyzing frames…"
                  : item.status === "ready"
                    ? "Analyze again"
                    : item.status === "failed"
                      ? "Retry analysis"
                      : "Analyze format"}
              </button>
              <button
                type="button"
                disabled={disabled || busy !== null || item.status !== "ready"}
                aria-pressed={selection === item.id}
                onClick={() => onSelect(item.id)}
              >
                {selection === item.id ? "Selected template" : "Use template"}
              </button>
            </div>
          </article>
        ))}
      </div>
      {filtered.length > limit && (
        <button type="button" onClick={() => setLimit((value) => value + 12)}>
          Show more clips ({filtered.length - limit})
        </button>
      )}
      <details className="studio-details">
        <summary>How template matching works</summary>
        <small>
          Classification uses sampled frames and your configured Ollama vision
          model. Sound is not analyzed; pacing is inferred. Captions are
          described but are not added to generated videos.
        </small>
      </details>
    </section>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { framePlayerUrl, sequenceSampleUrl, studioApi } from "./api";
import type { FrameDefinition, FrameSequence } from "./api";

export function FrameLibrary({
  selected,
  onSelect,
  selectedTheme,
  onThemeSelect,
  sceneCount,
}: {
  sceneCount?: number;
  selected?: string;
  selectedTheme?: string;
  onThemeSelect?: (theme: string) => void;
  onSelect?: (id: string) => void;
}) {
  const [sequences, setSequences] = useState<FrameSequence[]>([]);
  const [frames, setFrames] = useState<FrameDefinition[]>([]);
  const [tab, setTab] = useState<"sequences" | "frames">(
    onSelect ? "sequences" : "frames",
  );
  const [playing, setPlaying] = useState("");
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);
  const [importStatus, setImportStatus] = useState("");
  const [query, setQuery] = useState("");
  const [volume, setVolume] = useState("All");
  const [localTheme, setLocalTheme] = useState("neon");
  const theme = selectedTheme ?? localTheme;
  const hasThemes = frames.some(
    (frame) => frame.volume === 2 && !frame.id.startsWith("html-"),
  );
  function setTheme(value: string) {
    setLocalTheme(value);
    onThemeSelect?.(value);
  }
  const [replay, setReplay] = useState(0);
  const [use, setUse] = useState("All");
  const matchingFrames = frames.filter(
    (frame) =>
      (use === "All" || frame.use === use) &&
      (volume === "All" || String(frame.volume) === volume) &&
      `${frame.name} ${frame.description} ${frame.use}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  useEffect(() => {
    let alive = true;
    void Promise.all([studioApi.sequences(), studioApi.frames()])
      .then(([a, b]) => {
        if (alive) {
          setSequences(a);
          setFrames(b);
        }
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, []);
  return (
    <section className="frame-library">
      <div className="studio-section-heading">
        <div>
          <span className="eyebrow">BUILT FOR A STORY, SCENE BY SCENE</span>
          <h2>{onSelect ? "Choose your template" : "Frame library"}</h2>
          <p>
            {sequences.length} sequences · {frames.length} animated scenes.
            Click inside a frame to replay it. Names, numbers and code in
            previews are illustrative placeholders.
          </p>
        </div>
      </div>
      {!onSelect && (
        <label className="studio-secondary-button">
          {importing ? "Importing…" : "Import HTML frames"}
          <input
            type="file"
            accept=".html,.htm,text/html"
            disabled={importing}
            onChange={async (event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (!file) return;
              setImporting(true);
              setError("");
              setImportStatus("");
              try {
                const result = await studioApi.importFrames(file);
                const [nextSequences, nextFrames] = await Promise.all([
                  studioApi.sequences(),
                  studioApi.frames(),
                ]);
                setSequences(nextSequences);
                setFrames(nextFrames);
                setQuery("");
                setVolume("All");
                setUse("All");
                setReplay((value) => value + 1);
                setImportStatus(
                  `Imported ${result.frames} scenes in ${result.sequences} ${result.sequences === 1 ? "sequence" : "sequences"}.`,
                );
              } catch (error) {
                setError(
                  error instanceof Error
                    ? error.message
                    : "Could not import frames",
                );
              } finally {
                setImporting(false);
              }
            }}
          />
          <small>
            HTML sequence files with embedded styles and const T scene data, up
            to 2 MB.
          </small>
        </label>
      )}
      {importStatus && <p role="status">{importStatus}</p>}
      {!onSelect && (
        <div className="studio-tabs" role="group" aria-label="Browse frames">
          <button
            aria-pressed={tab === "sequences"}
            onClick={() => setTab("sequences")}
          >
            Complete sequences
          </button>
          <button
            aria-pressed={tab === "frames"}
            onClick={() => setTab("frames")}
          >
            Individual frames ({frames.length})
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!error && sequences.length === 0 && (
        <p role="status">Loading frame previews…</p>
      )}
      {onSelect && hasThemes && (
        <label className="frame-theme-picker">
          Volume 2 theme
          <select
            value={theme}
            onChange={(event) => setTheme(event.target.value)}
          >
            {[
              ["neon", "Neon Violet"],
              ["paper", "Paper Pop"],
              ["sunset", "Sunset Gradient"],
              ["cyan", "Terminal Cyan"],
              ["amber", "Amber Cards"],
              ["glass", "Glass Light"],
              ["mono", "Mono Teal"],
            ].map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
      )}
      {tab === "sequences" && (
        <div className="frame-sequence-list">
          {sequences
            .filter(
              (sequence) =>
                !sceneCount || sequence.frames.length === sceneCount,
            )
            .map((sequence) => (
              <article
                key={sequence.id}
                className={`frame-sequence-card ${selected === sequence.id ? "is-selected" : ""}`}
              >
                <div className="studio-section-heading">
                  <div>
                    <span className="eyebrow">
                      {sequence.durations.reduce(
                        (total, seconds) => total + seconds,
                        0,
                      )}{" "}
                      SECONDS · {sequence.frames.length} SCENES · FACELESS
                    </span>
                    <h3>{sequence.name}</h3>
                    <p>{sequence.description}</p>
                  </div>
                  <div className="frame-palette" aria-label="Sequence colors">
                    {[
                      sequence.background,
                      sequence.accent,
                      sequence.secondary,
                    ].map((color) => (
                      <span key={color} style={{ background: color }} />
                    ))}
                  </div>
                </div>
                {playing === sequence.id ? (
                  <div className="frame-sample-player">
                    <video
                      controls
                      autoPlay
                      playsInline
                      preload="metadata"
                      src={sequenceSampleUrl(sequence.id, theme)}
                      aria-label={`${sequence.name} motion preview`}
                    />
                    <button onClick={() => setPlaying("")}>
                      Back to frames
                    </button>
                  </div>
                ) : (
                  <div
                    className="frame-strip"
                    aria-label={`${sequence.name} scene sequence`}
                  >
                    {sequence.frames.map((id, i) => (
                      <figure key={`${id}-${i}`}>
                        <iframe
                          className="frame-design-player"
                          loading="lazy"
                          sandbox="allow-scripts"
                          src={framePlayerUrl(id, sequence.id, theme)}
                          title={`${i + 1}. ${frames.find((f) => f.id === id)?.name ?? id}`}
                        />
                        <figcaption>
                          <strong>
                            {frames.find((f) => f.id === id)?.name ?? id}
                          </strong>
                          <span>{sequence.durations[i]}s</span>
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                )}
                <div className="studio-card-actions">
                  <small>{sequence.font} · animation and illustrations</small>
                  <button
                    className="studio-secondary-button"
                    onClick={() =>
                      setPlaying(playing === sequence.id ? "" : sequence.id)
                    }
                  >
                    Preview motion
                  </button>
                  {onSelect ? (
                    <button
                      className={
                        selected === sequence.id
                          ? "studio-selected-button"
                          : "primary-button"
                      }
                      aria-pressed={selected === sequence.id}
                      onClick={() => onSelect(sequence.id)}
                    >
                      {selected === sequence.id
                        ? "Selected"
                        : "Use this template"}
                    </button>
                  ) : (
                    <Link
                      className="primary-link"
                      href={`/create?sequence=${sequence.id}&theme=${theme}`}
                    >
                      Create with these frames
                    </Link>
                  )}
                </div>
              </article>
            ))}
        </div>
      )}
      {tab === "frames" && (
        <>
          <div className="frame-library-filters">
            <label>
              Collection
              <select
                value={volume}
                onChange={(event) => setVolume(event.target.value)}
              >
                <option value="All">
                  All collections · {frames.length} designs
                </option>
                {[...new Set(frames.map((frame) => frame.volume))].map((id) => (
                  <option key={id} value={id}>
                    Volume {id}
                  </option>
                ))}
              </select>
            </label>
            {hasThemes && (
              <label>
                Volume 2 theme
                <select
                  value={theme}
                  onChange={(event) => setTheme(event.target.value)}
                >
                  {[
                    ["neon", "Neon Violet"],
                    ["paper", "Paper Pop"],
                    ["sunset", "Sunset Gradient"],
                    ["cyan", "Terminal Cyan"],
                    ["amber", "Amber Cards"],
                    ["glass", "Glass Light"],
                    ["mono", "Mono Teal"],
                  ].map(([id, name]) => (
                    <option value={id} key={id}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Find a frame
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search type, diagrams, demos…"
              />
            </label>
            <label>
              Story beat
              <select
                value={use}
                onChange={(event) => setUse(event.target.value)}
              >
                {["All", ...new Set(frames.map((frame) => frame.use))].map(
                  (beat) => (
                    <option key={beat}>{beat}</option>
                  ),
                )}
              </select>
            </label>
          </div>
          <button
            className="studio-secondary-button"
            onClick={() => setReplay(replay + 1)}
          >
            Replay all frames
          </button>
          {matchingFrames.length === 0 && frames.length > 0 && (
            <p role="status">
              No frames match. Try another search or story beat.
            </p>
          )}
          <div className="individual-frame-grid">
            {matchingFrames.map((frame) => (
              <article className="individual-frame-card" key={frame.id}>
                <iframe
                  key={`${frame.id}-${theme}-${replay}`}
                  className="frame-design-player"
                  loading="lazy"
                  sandbox="allow-scripts"
                  src={framePlayerUrl(
                    frame.id,
                    sequences.find((s) => s.frames.includes(frame.id))?.id,
                    theme,
                  )}
                  title={frame.name}
                />
                <span className="eyebrow">
                  Vol. {frame.volume} · {frame.use}
                </span>
                <h3>{frame.name}</h3>
                <p>{frame.description}</p>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

export function FramesPage() {
  return (
    <main className="page short-studio-page">
      <div className="studio-page-heading">
        <div>
          <span className="eyebrow">REACHCUT STUDIO</span>
          <h1>A frame for every beat.</h1>
          <p>Your voice. A visual for every idea. No camera required.</p>
        </div>
        <Link className="primary-link" href="/create">
          Create a short
        </Link>
      </div>
      <FrameLibrary />
    </main>
  );
}

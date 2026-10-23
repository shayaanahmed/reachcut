"use client";

import { useEffect, useState } from "react";
import { framePlayerUrl, studioApi } from "./api";
import type { FrameKind, FrameSequence, FrameDefinition } from "./api";

export type FrameSelection = {
  mode: "ai" | "manual";
  sequence: string;
  theme: string;
  frames: FrameKind[];
};
export const defaultSelection: FrameSelection = {
  mode: "ai",
  sequence: "html-d189115ff61aab9d",
  theme: "neon",
  frames: [
    "html-d189115ff61aab9d-1",
    "html-d189115ff61aab9d-2",
    "html-d189115ff61aab9d-3",
    "html-d189115ff61aab9d-4",
    "html-d189115ff61aab9d-5",
  ],
};
const beats = [
  "Hook",
  "Purpose",
  "Example",
  "How it works",
  "Outcome",
  "Closing question",
];

export function FramePicker({
  value,
  onChange,
}: {
  value: FrameSelection;
  onChange: (next: FrameSelection) => void;
}) {
  const [frames, setFrames] = useState<FrameDefinition[]>([]);
  const [sequences, setSequences] = useState<FrameSequence[]>([]);
  const [active, setActive] = useState(0);
  const [replay, setReplay] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    void Promise.all([studioApi.frames(), studioApi.sequences()])
      .then(([f, s]) => {
        if (alive) {
          setFrames(f);
          setSequences(s);
        }
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (
      sequences.length &&
      !sequences.some((sequence) => sequence.id === value.sequence)
    ) {
      onChange({
        ...value,
        sequence: sequences[0].id,
        frames: sequences[0].frames,
      });
    }
  }, [sequences, value, onChange]);
  const selected = frames.find((f) => f.id === value.frames[active]);
  return (
    <section className="frame-picker">
      <div className="studio-section-heading">
        <div>
          <span className="eyebrow">YOUR VISUAL STYLE</span>
          <h2>Choose your frames</h2>
          <p>Let AI match the story, or choose a design for each scene.</p>
        </div>
      </div>
      <div
        className="frame-mode-switch"
        role="group"
        aria-label="Frame selection mode"
      >
        <button
          aria-pressed={value.mode === "ai"}
          onClick={() => onChange({ ...value, mode: "ai" })}
        >
          <strong>✦ Let AI choose</strong>
          <span>A mix of designs suited to your story</span>
        </button>
        <button
          aria-pressed={value.mode === "manual"}
          onClick={() => onChange({ ...value, mode: "manual" })}
        >
          <strong>▦ Choose myself</strong>
          <span>Pick a preset, then fine-tune each scene</span>
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="frame-picker-layout">
        <div className="frame-picker-controls">
          {value.mode === "ai" ? (
            <div className="frame-auto-note">
              <span className="frame-auto-symbol" aria-hidden="true">
                ✦
              </span>
              <h3>A different visual for every idea</h3>
              <p>
                AI will choose frames from your library when it builds the
                storyboard. You can change them afterwards.
              </p>
              <p className="muted">
                Browse the example scenes here to get a feel for the designs.
              </p>
            </div>
          ) : (
            <>
              <label>
                Start with a preset
                <select
                  value={value.sequence}
                  onChange={(e) => {
                    const preset = sequences.find(
                      (s) => s.id === e.target.value,
                    );
                    if (preset) {
                      setActive(0);
                      onChange({
                        ...value,
                        sequence: preset.id,
                        frames: preset.frames,
                      });
                    }
                  }}
                >
                  {sequences.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <p>Choose a scene below, then change its frame.</p>
            </>
          )}
          <div
            className="frame-scene-slots"
            role="group"
            aria-label="Story scenes"
          >
            {value.frames.map((id, i) => (
              <button
                key={i}
                aria-pressed={active === i}
                aria-label={`Scene ${i + 1}: ${i === value.frames.length - 1 ? "Closing" : beats[i]}`}
                onClick={() => setActive(i)}
              >
                <span className="frame-slot-number">{i + 1}</span>
                <span>
                  <strong>
                    {i === value.frames.length - 1 ? "Closing" : beats[i]}
                  </strong>
                  <small>{frames.find((f) => f.id === id)?.name ?? id}</small>
                </span>
                {active === i && <span aria-hidden="true">✓</span>}
              </button>
            ))}
          </div>
          {value.mode === "manual" && (
            <label>
              Frame for scene {active + 1}
              <select
                value={value.frames[active]}
                onChange={(e) =>
                  onChange({
                    ...value,
                    frames: value.frames.map((id, i) =>
                      i === active ? (e.target.value as FrameKind) : id,
                    ),
                  })
                }
              >
                {frames
                  .filter(
                    (f) =>
                      active === value.frames.length - 1 ||
                      f.id !== "story-poll",
                  )
                  .map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
              </select>
            </label>
          )}
          {frames.some(
            (frame) => frame.volume === 2 && !frame.id.startsWith("html-"),
          ) && (
            <label>
              Volume 2 colors
              <select
                value={value.theme}
                onChange={(e) => onChange({ ...value, theme: e.target.value })}
              >
                {[
                  ["neon", "Neon violet"],
                  ["paper", "Paper pop"],
                  ["sunset", "Sunset"],
                  ["cyan", "Terminal cyan"],
                  ["amber", "Amber cards"],
                  ["glass", "Glass light"],
                  ["mono", "Mono teal"],
                ].map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <div className="frame-picker-preview">
          <span className="frame-selection-badge">
            {value.mode === "manual" ? "✓ Selected" : "Example preview"} · Scene{" "}
            {active + 1}
          </span>
          <iframe
            key={`${active}-${replay}`}
            className="frame-design-player"
            sandbox="allow-scripts"
            title={`Preview: ${selected?.name ?? value.frames[active]}`}
            src={framePlayerUrl(
              value.frames[active],
              value.sequence,
              value.theme,
            )}
          />
          <strong>{selected?.name ?? value.frames[active]}</strong>
          <p>{selected?.description}</p>
          <button
            className="studio-secondary-button"
            onClick={() => setReplay(replay + 1)}
          >
            ↻ Replay preview
          </button>
          <small>Sample content. Your story replaces these labels.</small>
        </div>
      </div>
    </section>
  );
}

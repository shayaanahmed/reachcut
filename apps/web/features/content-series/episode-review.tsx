"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { request, upload } from "../informative/api";
import type {
  Providers,
  Script,
  Short,
  ShortSettings,
} from "../informative/api";
import { ShortReview } from "../informative/short-review";
import { episodeThumbnailUrl, visualUrl } from "./api";
import type { EpisodeDetail } from "./api";
import { VoicePicker } from "./voice-picker";
import { studioApi } from "../short-studio/api";
import { ThumbnailPreview } from "./thumbnail-preview";
import { FramePicker, defaultSelection } from "../short-studio/frame-picker";
import type { FrameSelection } from "../short-studio/frame-picker";

export function EpisodeReview({
  detail,
  onChange,
  onStartOver,
  providers,
  onRegenerate = () => {},
}: {
  detail: EpisodeDetail;
  onChange: (d: EpisodeDetail) => void;
  onStartOver: () => void;
  providers: Providers | null;
  onRegenerate?: (jobId: string) => void;
}) {
  const { short, episode } = detail;
  const [script, setScript] = useState(short.script as Script);
  const [settings, setSettings] = useState<ShortSettings>(short.settings);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [selection, setSelection] = useState<FrameSelection>(() => ({
    ...defaultSelection,
    mode: "manual",
    sequence: episode?.style.id ?? defaultSelection.sequence,
    theme: episode?.style.frame_sequence?.theme ?? "neon",
    frames: episode?.plan.visuals.every((v) => v.frame)
      ? episode.plan.visuals.map((v) => v.frame!.template)
      : defaultSelection.frames,
  }));
  const regenerationKey = useRef("");
  const running = [
    "queued",
    "producing",
    "generating",
    "cancel_requested",
  ].includes(short.status);
  const dirty = JSON.stringify(script) !== JSON.stringify(short.script);
  const settingsDirty =
    JSON.stringify(settings) !== JSON.stringify(short.settings);
  const busy = pending || running;
  async function act(operation: () => Promise<void>) {
    if (pending) return;
    setPending(true);
    setError("");
    try {
      await operation();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not complete this action",
      );
    } finally {
      setPending(false);
    }
  }
  function update(item: Short) {
    onChange({ ...detail, short: item });
  }
  if (!episode)
    return (
      <ShortReview short={short} onChange={update} onStartOver={onStartOver} />
    );
  const missingUploads = episode.plan.visuals.filter(
    (visual) =>
      visual.kind === "recording" && !short.artifacts[visual.section_id]?.asset,
  );
  const voiceReady =
    settings.narration_mode === "none" ||
    Boolean(settings.profile_id && providers?.narration.connected);
  return (
    <>
      <section className="settings-card series-panel">
        <span className="eyebrow">
          {episode.series.name} · {episode.style.name}
        </span>
        <h2>{short.topic}</h2>
        <p>{episode.angle.focus}</p>
        <p>Subject: {episode.brief.subject}</p>
        {episode.plan.concept && (
          <details>
            <summary>What this story explains</summary>
            <dl>
              <dt>The everyday problem</dt>
              <dd>{episode.plan.concept.problem}</dd>
              <dt>What it does</dt>
              <dd>{episode.plan.concept.purpose}</dd>
              <dt>How it helps</dt>
              <dd>{episode.plan.concept.benefit}</dd>
              <dt>How it works</dt>
              <dd>{episode.plan.concept.how_it_works}</dd>
              <dt>What you could do with it</dt>
              <dd>{episode.plan.concept.possible_result}</dd>
              <dt>Keep in mind</dt>
              <dd>{episode.plan.concept.limitation}</dd>
            </dl>
          </details>
        )}
        <details>
          <summary>Sources used for this video</summary>
          {episode.brief.sources.map((source) => (
            <article key={source.id}>
              <a href={source.url} target="_blank" rel="noreferrer">
                {source.title}
              </a>
              <pre className="series-source-text">{source.text}</pre>
            </article>
          ))}
          {episode.brief.sources.length === 0 && (
            <p>
              This storyboard uses your supplied notes. Review its factual
              accuracy.
            </p>
          )}
        </details>
      </section>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {pending && (
        <p className="studio-progress-notice" role="status">
          Saving your request… You can keep browsing the previews.
        </p>
      )}
      {(running ||
        short.has_output ||
        ["failed", "cancelled"].includes(short.status)) && (
        <ShortReview
          short={short}
          onChange={update}
          onStartOver={onStartOver}
          hideResume
        />
      )}
      <details className="settings-card frame-revision-panel">
        <summary>
          Change frames{" "}
          {short.has_output ? "and make a new version" : "for this storyboard"}
        </summary>
        <FramePicker
          value={selection}
          onChange={(value) => {
            setSelection(value);
            regenerationKey.current = "";
          }}
        />
        <p>Your narration is kept. The new version is saved separately.</p>
        {running && (
          <p role="status">
            You can explore designs now. Stop or finish this render before
            applying changes.
          </p>
        )}
        <button
          className="primary-button"
          disabled={running || dirty || settingsDirty}
          aria-disabled={pending}
          onClick={() => {
            if (pending) return;
            void act(async () => {
              regenerationKey.current ||= crypto.randomUUID();
              const job = await studioApi.storyboard({
                brief_id: episode.brief.id,
                storyline_id: episode.angle.id,
                sequence_id: selection.sequence,
                theme: selection.theme,
                frame_mode: selection.mode,
                ...(selection.mode === "manual"
                  ? { frames: selection.frames }
                  : {}),
                source_short_id: short.id,
                request_key: regenerationKey.current,
                feedback: "",
              });
              onRegenerate(job.id);
            });
          }}
        >
          {pending ? "Saving your task…" : "Apply frames to a new version"}
        </button>
      </details>
      {(!short.has_output ||
        (short.final_review && short.final_review.status !== "passed")) && (
        <section className="settings-card series-panel">
          <h2>Your storyboard</h2>
          {Boolean(episode.plan.editorial_notes?.length) && (
            <aside
              className="studio-editorial-notes"
              aria-label="Editorial suggestions"
            >
              <strong>
                Your storyboard is ready. A few lines may benefit from editing.
              </strong>
              <p>
                These are writing suggestions. Open “Edit this scene” below to
                make changes.
              </p>
              <ul>
                {episode.plan.editorial_notes?.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            </aside>
          )}
          <p>Preview the scenes. Open a scene to edit its narration.</p>
          <details className="studio-regenerator">
            <summary>Rewrite the story with AI</summary>
            <label>
              Try a different storyboard
              <textarea
                value={feedback}
                maxLength={3000}
                rows={2}
                placeholder="e.g. Open with an everyday problem, use a surprising example, keep the wording simple…"
                disabled={busy}
                onChange={(e) => {
                  setFeedback(e.target.value);
                  regenerationKey.current = "";
                }}
              />
            </label>
            <button
              disabled={busy || dirty || settingsDirty}
              onClick={() =>
                void act(async () => {
                  regenerationKey.current ||= crypto.randomUUID();
                  const brief = await studioApi.brief(episode.brief.id);
                  const job = await studioApi.storyboard({
                    brief_id: brief.id,
                    storyline_id: episode.angle.id,
                    sequence_id: episode.style.id,
                    request_key: regenerationKey.current,
                    feedback,
                    theme: selection.theme,
                    frame_mode: selection.mode,
                    ...(selection.mode === "manual"
                      ? { frames: selection.frames }
                      : {}),
                  });
                  onRegenerate(job.id);
                })
              }
            >
              {pending
                ? "Working with Ollama…"
                : "Regenerate storyboard with Ollama"}
            </button>
            <small>
              Your selected template and research are reused. The previous draft
              is kept.
            </small>
          </details>
          <div className="series-storyboard compact-storyboard">
            {script.sections?.map((section, i) => {
              const visual = episode.plan.visuals.find(
                (v) => v.section_id === section.id,
              );
              return (
                <article className="series-scene" key={section.id}>
                  <h3>
                    {i + 1}. {section.heading}
                  </h3>
                  <Image
                    unoptimized
                    className="series-storyboard-image"
                    src={visualUrl(short.id, section.id)}
                    alt={`Storyboard: ${visual?.heading ?? section.heading}`}
                    width={270}
                    height={480}
                  />
                  <p>{section.text}</p>
                  {visual?.frame &&
                    ["photo", "poll"].includes(visual.frame.template) && (
                      <small>
                        Layout preview. Ollama creates an illustration for this
                        story during video creation.
                      </small>
                    )}
                  {visual?.frame && (
                    <p className="eyebrow">
                      {visual.frame.template} · {visual.frame.duration_seconds}s
                    </p>
                  )}
                  {visual?.kind === "illustration" && !visual.frame && (
                    <>
                      <small>
                        {episode.style.design?.reuse_background
                          ? "Uses your selected template background."
                          : episode.series.artwork_mode === "ollama"
                            ? "Layout preview. Ollama creates the illustration during production."
                            : "Designed explanation preview."}
                      </small>
                      <details>
                        <summary>Planned illustration</summary>
                        <p>{visual.art_prompt}</p>
                      </details>
                    </>
                  )}
                  <details>
                    <summary>Edit this scene</summary>
                    <label>
                      Narration — {section.heading}
                      <textarea
                        disabled={busy}
                        rows={5}
                        maxLength={2000}
                        value={section.text}
                        onChange={(e) =>
                          setScript({
                            ...script,
                            sections: script.sections.map((s, index) =>
                              index === i ? { ...s, text: e.target.value } : s,
                            ),
                          })
                        }
                      />
                    </label>
                    {section.claims.length > 0 && (
                      <details>
                        <summary>Supporting excerpts</summary>
                        {section.claims.map((claim, index) => (
                          <blockquote key={index}>{claim.quote}</blockquote>
                        ))}
                      </details>
                    )}
                    <label>
                      Add screenshot or recording
                      <input
                        disabled={busy}
                        type="file"
                        accept="image/png,image/jpeg,image/webp,video/mp4,video/quicktime,video/webm"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file)
                            void act(async () =>
                              update(
                                await upload(
                                  short.id,
                                  section.id,
                                  file.type.startsWith("video/")
                                    ? "recording"
                                    : "image",
                                  file,
                                ),
                              ),
                            );
                        }}
                      />
                    </label>
                  </details>
                  {short.artifacts[section.id]?.asset && (
                    <small>
                      Visual asset attached. It will be used during rendering.
                    </small>
                  )}
                </article>
              );
            })}
          </div>
          {dirty && (
            <button
              disabled={
                busy || !dirty || script.sections.some((s) => !s.text.trim())
              }
              onClick={() =>
                void act(async () =>
                  update(
                    await request<Short>(
                      `/shorts/${short.id}/script`,
                      "PUT",
                      script,
                    ),
                  ),
                )
              }
            >
              Save script edits
            </button>
          )}
          {short.script_issues.map((issue, i) => (
            <p key={i} role="alert">
              {issue.section}: {issue.message}
            </p>
          ))}
          <details>
            <summary>Add a voice with VoiceBox (optional)</summary>
            <VoicePicker
              settings={settings}
              onChange={setSettings}
              providers={providers}
              disabled={busy}
            />
            <button
              disabled={busy || dirty || !settingsDirty}
              onClick={() =>
                void act(async () =>
                  update(
                    await request<Short>(
                      `/shorts/${short.id}/settings`,
                      "PUT",
                      settings,
                    ),
                  ),
                )
              }
            >
              Save video voice settings
            </button>
          </details>
          {settings.narration_mode === "none" && (
            <p>
              This version uses music and on-screen text. Add a VoiceBox voice
              above for a narrated video.
            </p>
          )}
          <div className="creation-actions">
            <button
              className="primary-button"
              disabled={
                busy ||
                dirty ||
                settingsDirty ||
                !voiceReady ||
                missingUploads.length > 0 ||
                short.script_issues.length > 0
              }
              onClick={() =>
                void act(async () => {
                  await request(`/shorts/${short.id}/script/approve`, "POST");
                  update(
                    await request<Short>(`/shorts/${short.id}/produce`, "POST"),
                  );
                })
              }
            >
              {settings.narration_mode === "none"
                ? "Create music-only video"
                : "Create narrated video"}
            </button>
          </div>
          {!voiceReady && (
            <p>
              Connect VoiceBox and choose a voice, or create a music-only video
              and add narration later.
            </p>
          )}
        </section>
      )}
      <section className="settings-card series-panel">
        <details>
          <summary>Thumbnail & download</summary>
          <ThumbnailPreview
            design={episode.series.thumbnail}
            name={episode.series.name}
            subject={episode.brief.subject}
            headline={episode.plan.headline}
          />
          <a href={episodeThumbnailUrl(short.id)} download>
            Download video thumbnail
          </a>
        </details>
      </section>
      {!running && !short.has_output && missingUploads.length > 0 && (
        <p>
          Attach a screenshot or recording for:{" "}
          {missingUploads.map((visual) => visual.heading).join(", ")}
        </p>
      )}
      {!running && !short.has_output && (
        <button onClick={onStartOver}>Start another short</button>
      )}
    </>
  );
}

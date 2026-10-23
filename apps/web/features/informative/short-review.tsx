"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { request, shortVideoUrl, deleteShort } from "./api";
import type { Providers, Script, Short } from "./api";
import { matchesVoiceModel } from "./voice-models";

import { JobProgress } from "../short-studio/job-progress";

const activeStatuses = [
  "queued",
  "producing",
  "generating",
  "cancel_requested",
];

export function ShortReview({
  short,
  onChange,
  onStartOver,
  hideResume = false,
}: {
  short: Short;
  onChange: (short: Short) => void;
  onStartOver?: () => void;
  hideResume?: boolean;
}) {
  const [script, setScript] = useState(short.script as Script);
  const [providers, setProviders] = useState<Providers | null>(null);
  const [profile, setProfile] = useState(short.settings.profile_id);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [voiceModel, setVoiceModel] = useState("");
  const engine = providers?.narration.engines.find((e) =>
    voiceModel
      ? e.model_name === voiceModel
      : matchesVoiceModel(e, short.settings),
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const running = activeStatuses.includes(short.status);
  const busy = pending || running;
  const unsaved = JSON.stringify(script) !== JSON.stringify(short.script);

  useEffect(() => {
    if (!running) return;
    let alive = true;
    const timer = window.setInterval(() => {
      void request<Short>(`/shorts/${short.id}`)
        .then((item) => {
          if (alive) onChange(item);
        })
        .catch((e: Error) => {
          if (alive) setError(e.message);
        });
    }, 2500);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [short.id, running, onChange]);

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
  async function produce() {
    if (!short.approved)
      await request(`/shorts/${short.id}/script/approve`, "POST");
    onChange(await request<Short>(`/shorts/${short.id}/produce`, "POST"));
  }

  if (deleted)
    return (
      <p role="status">
        Video deleted. <Link href="/created">Back to created videos</Link>
      </p>
    );

  return (
    <>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <section className="settings-card creation-form">
        {pending && <p role="status">Saving your request…</p>}
        <h2>
          {running
            ? "Creating and reviewing your video"
            : short.has_output
              ? short.status === "failed" ||
                (short.final_review && short.final_review.status !== "passed")
                ? "Your video needs refinement"
                : "Your video is ready"
              : "Creating your video"}
        </h2>
        {running ? (
          <JobProgress kind="video" phase={short.phase} />
        ) : (
          <p role="status">{short.phase}</p>
        )}
        {short.error && (
          <p className="error" role="alert">
            {short.error}
          </p>
        )}
        {running && (
          <button
            disabled={pending || short.status === "cancel_requested"}
            onClick={() =>
              void act(async () => {
                onChange(
                  await request<Short>(`/shorts/${short.id}/cancel`, "POST"),
                );
              })
            }
          >
            Stop generation
          </button>
        )}
        {!hideResume &&
          ["failed", "cancelled", "draft"].includes(short.status) && (
            <button
              disabled={busy || unsaved}
              onClick={() => void act(produce)}
            >
              Resume production
            </button>
          )}
        {short.has_output && (
          <>
            <video
              className="informative-preview"
              controls
              src={shortVideoUrl(short.id)}
            />
            {short.final_review && (
              <section
                className="settings-card"
                aria-label="Final AI video review"
              >
                <h3>
                  {short.final_review.status === "passed"
                    ? "AI review passed"
                    : "AI review needs attention"}
                </h3>
                <p>
                  {short.final_review.assessment?.summary ??
                    short.final_review.error}
                </p>
                {short.final_review.assessment && (
                  <dl className="studio-review-scores">
                    {[
                      ["Hook", short.final_review.assessment.hook_score],
                      ["Clarity", short.final_review.assessment.clarity_score],
                      ["Pacing", short.final_review.assessment.pacing_score],
                      [
                        "Shareability",
                        short.final_review.assessment.shareability_score,
                      ],
                    ].map(([label, score]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd>{score}/100</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {short.final_review.assessment?.issues.map((issue, index) => (
                  <p key={index}>
                    Scene {issue.scene}: {issue.message}
                  </p>
                ))}
                <small>
                  {short.final_review.basis
                    ? `${short.final_review.basis}. `
                    : ""}
                  Editorial assessment of appeal, not a prediction of virality.
                </small>
                {short.final_review.history && (
                  <p>
                    {short.final_review.history.length} review passes ·
                    automatic refinements preserve your narration and template.
                  </p>
                )}
                {short.final_review.status !== "passed" && !running && (
                  <button disabled={pending} onClick={() => void act(produce)}>
                    Retry final review and refinement
                  </button>
                )}
              </section>
            )}
            {short.findings.map((f, i) => (
              <p key={i}>{f.message}</p>
            ))}
            <div className="creation-actions">
              <a href={shortVideoUrl(short.id)} download>
                Download video
              </a>
              {short.status === "review" &&
                (!short.final_review ||
                  short.final_review.status === "passed") && (
                  <button
                    className="primary-button"
                    disabled={busy || unsaved}
                    onClick={() =>
                      void act(async () => {
                        const result = await request<{
                          publishing_path: string;
                        }>(`/shorts/${short.id}/approve`, "POST");
                        window.location.assign(
                          result.publishing_path.replace(
                            /\/publish(?:\?.*)?$/,
                            "",
                          ),
                        );
                      })
                    }
                  >
                    Reviewed — open clip editor
                  </button>
                )}
              {short.publication_project_id && (
                <Link href={`/projects/${short.publication_project_id}`}>
                  Open clips and publishing
                </Link>
              )}
            </div>
            <button
              disabled={busy}
              aria-expanded={voiceOpen}
              onClick={() => {
                setVoiceOpen(!voiceOpen);
                if (!voiceOpen)
                  void act(async () =>
                    setProviders(await request<Providers>("/shorts/providers")),
                  );
              }}
            >
              Add or change voice-over
            </button>
          </>
        )}
      </section>
      {voiceOpen && (
        <section className="settings-card creation-form">
          <h2>Optional voice-over</h2>
          <p>
            Use VoiceBox to narrate your video. The existing visuals are reused.
          </p>
          {providers && !providers.narration.connected && (
            <p role="status">
              VoiceBox is offline. Start it at the configured URL in Settings,
              then reopen these controls.
            </p>
          )}
          {script.sections?.map((section, i) => (
            <label key={section.id}>
              {section.heading}
              <textarea
                value={section.text}
                disabled={busy}
                maxLength={2000}
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
          ))}
          <button
            disabled={
              busy || !unsaved || script.sections.some((s) => !s.text.trim())
            }
            onClick={() =>
              void act(async () => {
                onChange(
                  await request<Short>(
                    `/shorts/${short.id}/script`,
                    "PUT",
                    script,
                  ),
                );
              })
            }
          >
            Save voice-over script
          </button>
          <label>
            VoiceBox voice
            <select
              value={profile}
              disabled={busy}
              onChange={(e) => setProfile(e.target.value)}
            >
              <option value="">Choose a voice</option>
              {providers?.narration.profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            VoiceBox engine and model
            <select
              disabled={busy}
              value={engine?.model_name ?? ""}
              onChange={(e) => setVoiceModel(e.target.value)}
            >
              <option value="">Choose an installed voice model</option>
              {providers?.narration.engines.map((e) => (
                <option
                  key={e.model_name}
                  value={e.model_name}
                  disabled={!e.downloaded}
                >
                  {e.display_name}
                  {!e.downloaded ? " · install in VoiceBox" : ""}
                </option>
              ))}
            </select>
          </label>
          <p>
            Voice models must be installed in VoiceBox. Configure the engine and
            model in Settings.
          </p>
          <Link href="/settings/general">Narration settings</Link>
          <button
            className="primary-button"
            disabled={
              busy ||
              unsaved ||
              !profile ||
              !engine?.downloaded ||
              !providers?.narration.connected
            }
            onClick={() =>
              void act(async () => {
                const updated = await request<Short>(
                  `/shorts/${short.id}/settings`,
                  "PUT",
                  {
                    ...short.settings,
                    profile_id: profile,
                    narration_mode: "voicebox",
                    engine: engine?.engine ?? short.settings.engine,
                    model_size: engine?.model_name.includes("0.6B")
                      ? "0.6B"
                      : engine?.model_name.toLowerCase().includes("3b")
                        ? "3B"
                        : engine?.engine === "tada"
                          ? "1B"
                          : "1.7B",
                    delivery: engine?.supports_delivery
                      ? short.settings.delivery
                      : "",
                  },
                );
                onChange(updated);
                await request(`/shorts/${short.id}/script/approve`, "POST");
                onChange(
                  await request<Short>(`/shorts/${short.id}/produce`, "POST"),
                );
              })
            }
          >
            Create narrated version
          </button>
        </section>
      )}
      {!running && (
        <div className="video-delete-controls">
          {confirmDelete ? (
            <>
              <p>
                Delete this video and its local files? Published copies stay
                available.
              </p>
              <button
                disabled={pending}
                onClick={() =>
                  void act(async () => {
                    await deleteShort(short.id);
                    if (onStartOver) onStartOver();
                    else setDeleted(true);
                  })
                }
              >
                Confirm delete
              </button>
              <button onClick={() => setConfirmDelete(false)}>
                Keep video
              </button>
            </>
          ) : (
            <button
              className="studio-text-button danger"
              onClick={() => setConfirmDelete(true)}
            >
              Delete video
            </button>
          )}
        </div>
      )}
      {short.sources.length > 0 && (
        <details className="settings-card">
          <summary>Sources and references</summary>
          <p>
            Review these sources and any reference material against the video’s
            factual claims.
          </p>
          {short.sources.map((s) => (
            <p key={s.id}>
              <a href={s.url} target="_blank" rel="noreferrer">
                {s.title}
              </a>
            </p>
          ))}
        </details>
      )}
      {onStartOver ? (
        <button onClick={onStartOver}>Create another short</button>
      ) : (
        <Link href="/create">Create another short</Link>
      )}
    </>
  );
}

export function CreatedShorts() {
  const [shorts, setShorts] = useState<Short[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState("");
  const [confirmDelete, setConfirmDelete] = useState("");
  useEffect(() => {
    let alive = true;
    void request<Short[]>("/shorts")
      .then((items) => {
        if (alive) setShorts(items);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);
  return (
    <main className="page informative-workspace">
      <div className="page-heading">
        <div>
          <span className="eyebrow">REACHCUT</span>
          <h1>Created videos</h1>
          <p>
            Review your videos, add narration, or continue in the clip editor.
          </p>
        </div>
        <Link href="/create">Create a short</Link>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {loading ? (
        <p role="status">Loading videos…</p>
      ) : shorts.length === 0 && !error ? (
        <p>
          No videos yet. Share a GitHub repo or discover a tech trick to start.
        </p>
      ) : null}
      <div className="creation-options">
        {shorts.map((s) => (
          <article className="settings-card" key={s.id}>
            <h2>{s.topic}</h2>
            <p>{s.phase}</p>
            <p>{s.status}</p>
            {s.has_output && (
              <video
                className="created-video-preview"
                controls
                preload="metadata"
                src={shortVideoUrl(s.id)}
              />
            )}
            {!activeStatuses.includes(s.status) && (
              <div className="video-delete-controls">
                {confirmDelete === s.id ? (
                  <>
                    <p>
                      Delete this video and local files? Published copies are
                      kept.
                    </p>
                    <button
                      disabled={deleting === s.id}
                      onClick={async () => {
                        setDeleting(s.id);
                        setError("");
                        try {
                          await deleteShort(s.id);
                          setShorts((items) =>
                            items.filter((item) => item.id !== s.id),
                          );
                          setConfirmDelete("");
                        } catch (e) {
                          setError(
                            e instanceof Error
                              ? e.message
                              : "Could not delete video",
                          );
                        } finally {
                          setDeleting("");
                        }
                      }}
                    >
                      {deleting === s.id ? "Deleting…" : "Confirm delete"}
                    </button>
                    <button onClick={() => setConfirmDelete("")}>
                      Keep video
                    </button>
                  </>
                ) : (
                  <button
                    className="studio-text-button danger"
                    onClick={() => setConfirmDelete(s.id)}
                  >
                    Delete video
                  </button>
                )}
              </div>
            )}
            <Link href={`/create?short=${encodeURIComponent(s.id)}`}>
              Open video
            </Link>
            {s.publication_project_id && (
              <p>
                <Link href={`/projects/${s.publication_project_id}`}>
                  Clips and publishing
                </Link>
              </p>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}

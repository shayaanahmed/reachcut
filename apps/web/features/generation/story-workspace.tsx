"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { GeneratedVideo } from "../../lib/contracts";
import {
  renameGeneratedVideo,
  prepareStoryPublishing,
  stopGeneratedVideo,
  deleteGeneratedVideo,
  generatedVideoUrl,
  getGeneratedVideo,
  resumeGeneratedVideo,
} from "./api";

import { resumeSummary } from "./resume-summary";

const activeStatuses = new Set([
  "queued",
  "rendering",
  "finishing",
  "cancel_requested",
]);

export function StoryWorkspace({ videoId }: { videoId: string }) {
  const router = useRouter();
  const [video, setVideo] = useState<GeneratedVideo | null>(null);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getGeneratedVideo(videoId)
      .then(setVideo)
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, [videoId]);

  useEffect(() => {
    if (!video || !activeStatuses.has(video.status)) return;
    const timer = window.setInterval(() => {
      void getGeneratedVideo(video.id)
        .then(setVideo)
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [video]);

  if (loading)
    return (
      <main className="page">
        <div className="loading-card">Loading story project…</div>
      </main>
    );
  if (!video)
    return (
      <main className="page">
        <div className="empty-state">
          <h1>Story project not found</h1>
          <p>{error ?? "It may have been removed from this workspace."}</p>
          <Link className="primary-link" href="/stories">
            Back to story projects
          </Link>
        </div>
      </main>
    );

  const videoUrl = generatedVideoUrl(video);
  const progress = Math.round(video.progress * 100);
  const currentVideo = video;
  const recovery = resumeSummary(video);

  async function resume() {
    setPending(true);
    try {
      setVideo(await resumeGeneratedVideo(currentVideo.id));
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not resume story",
      );
    } finally {
      setPending(false);
    }
  }

  async function rename() {
    setPending(true);
    setError(null);
    try {
      setVideo(await renameGeneratedVideo(currentVideo.id, title.trim()));
      setEditing(false);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not rename short",
      );
    } finally {
      setPending(false);
    }
  }

  async function share() {
    setPending(true);
    setError(null);
    try {
      const destination = await prepareStoryPublishing(currentVideo.id);
      router.push(
        `/projects/${destination.project_id}/clips/${destination.clip_id}/publish`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not open publishing",
      );
    } finally {
      setPending(false);
    }
  }

  async function stop() {
    setPending(true);
    try {
      setVideo(await stopGeneratedVideo(currentVideo.id));
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not stop story",
      );
    } finally {
      setPending(false);
    }
  }

  async function remove() {
    if (
      !window.confirm(
        `Delete “${currentVideo.plan.title}” and its generated files?`,
      )
    )
      return;
    setPending(true);
    try {
      await deleteGeneratedVideo(currentVideo.id);
      router.push("/stories");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not delete story",
      );
      setPending(false);
    }
  }

  return (
    <main className="page story-workspace-page">
      <div className="breadcrumbs">
        <Link href="/stories">Story projects</Link>
        <span>/</span>
        <span>{video.plan.title}</span>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <header className="story-workspace-header">
        <div>
          <span className={`status ${video.status}`}>{video.status}</span>
          <h1>{video.plan.title}</h1>
          {editing && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void rename();
              }}
            >
              <label>
                Short title
                <input
                  aria-label="Short title"
                  value={title}
                  maxLength={100}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <button disabled={pending || !title.trim()}>Save title</button>
              <button
                type="button"
                disabled={pending}
                onClick={() => setEditing(false)}
              >
                Cancel
              </button>
            </form>
          )}
          <p>{video.plan.logline}</p>
        </div>
        <div className="story-workspace-actions">
          <Link href="/generate">＋ Create another</Link>
          {!activeStatuses.has(video.status) && (
            <button
              type="button"
              disabled={pending}
              onClick={() => {
                setTitle(video.plan.title);
                setEditing(true);
              }}
            >
              Rename
            </button>
          )}
          {activeStatuses.has(video.status) && (
            <button
              type="button"
              disabled={pending || video.status === "cancel_requested"}
              onClick={() => void stop()}
            >
              {video.status === "cancel_requested"
                ? "Stopping…"
                : "Stop project"}
            </button>
          )}
          {video.status === "complete" && (
            <button
              type="button"
              disabled={pending}
              onClick={() => void share()}
            >
              {pending ? "Opening publishing…" : "Share on social platforms"}
            </button>
          )}
          {["failed", "cancelled"].includes(video.status) && (
            <button
              className="primary-link"
              type="button"
              disabled={pending}
              onClick={() => void resume()}
            >
              {pending ? "Queueing recovery…" : recovery.label}
            </button>
          )}
          {videoUrl && (
            <a className="primary-link" href={videoUrl} download>
              Download MP4
            </a>
          )}
          {["failed", "complete", "cancelled"].includes(video.status) && (
            <button
              className="danger-button"
              type="button"
              disabled={pending}
              onClick={() => void remove()}
            >
              Delete
            </button>
          )}
        </div>
      </header>

      {["failed", "cancelled"].includes(video.status) && (
        <section className="studio-recovery" aria-label="Recovery checkpoint">
          <strong>{video.phase}</strong>
          <p>{recovery.detail}</p>
          {video.error && (
            <details>
              <summary>Technical error details</summary>
              <p>{video.error}</p>
            </details>
          )}
        </section>
      )}
      {activeStatuses.has(video.status) && (
        <p role="status" aria-live="polite">
          {video.phase}
        </p>
      )}
      <div className="story-workspace-layout">
        <section className="story-master-panel" aria-label="Story video master">
          <div
            className={`story-master-player ratio-${video.aspect_ratio.replace(":", "-")}`}
          >
            {videoUrl ? (
              <video
                src={videoUrl}
                controls
                playsInline
                aria-label={video.plan.title}
              />
            ) : (
              <div className="story-master-progress">
                <span>{progress}%</span>
                <strong>{video.phase}</strong>
                <div>
                  <i style={{ width: `${progress}%` }} />
                </div>
                <small>
                  {
                    video.scenes.filter((scene) => scene.status === "complete")
                      .length
                  }{" "}
                  of {video.scenes.length} scenes complete
                </small>
              </div>
            )}
          </div>
          <div className="story-master-meta">
            <span>
              <strong>{video.target_duration_seconds}s</strong> duration
            </span>
            <span>
              <strong>{video.aspect_ratio}</strong> frame
            </span>
            <span>
              <strong>{video.quality}</strong> quality
            </span>
            <span>
              <strong>{video.provider}</strong> renderer
            </span>
          </div>
        </section>

        <aside className="story-direction-panel">
          <span className="eyebrow">DIRECTOR&apos;S NOTES</span>
          <h2>Visual direction</h2>
          <p>{video.plan.visual_style}</p>
          <h3>Original story</h3>
          <p>{video.story}</p>
          <h3>Character bible</h3>
          <div className="story-character-list">
            {video.plan.characters.map((character) => (
              <article key={character.id}>
                <strong>{character.name}</strong>
                <small>{character.role}</small>
                <p>{character.appearance_anchor}</p>
                <span>{character.wardrobe_anchor}</span>
              </article>
            ))}
          </div>
        </aside>
      </div>

      <section
        className="story-scene-manager"
        aria-labelledby="story-scenes-heading"
      >
        <div className="section-heading">
          <div>
            <span className="eyebrow">PRODUCTION TIMELINE</span>
            <h2 id="story-scenes-heading">Scenes</h2>
          </div>
          <small>{video.scenes.length} connected shots</small>
        </div>
        <div className="story-scene-list">
          {video.scenes.map((scene) => (
            <article key={scene.id} className={scene.status}>
              <span>{String(scene.scene_index).padStart(2, "0")}</span>
              <div>
                <div>
                  <strong>{scene.title}</strong>
                  <b>{scene.status}</b>
                </div>
                <p>{scene.prompt}</p>
                <small>
                  {scene.duration_seconds}s · seed {scene.seed}
                </small>
                {scene.error && <em>{scene.error}</em>}
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { GeneratedVideo } from "../../lib/contracts";
import {
  stopGeneratedVideo,
  deleteGeneratedVideo,
  generatedVideoUrl,
  listGeneratedVideos,
  resumeGeneratedVideo,
} from "./api";

import { resumeSummary } from "./resume-summary";

type StoryFilter = "all" | "active" | "complete" | "failed";
type StorySort = "recent" | "oldest" | "attention";

const activeStatuses = new Set([
  "queued",
  "rendering",
  "finishing",
  "cancel_requested",
]);

function matchesFilter(video: GeneratedVideo, filter: StoryFilter) {
  if (filter === "active") return activeStatuses.has(video.status);
  if (filter === "complete") return video.status === "complete";
  if (filter === "failed") return video.status === "failed";
  return true;
}

function progressFor(video: GeneratedVideo) {
  if (video.status === "complete") return 100;
  const completed = video.scenes.filter(
    (scene) => scene.status === "complete",
  ).length;
  return Math.max(
    Math.round(video.progress * 100),
    video.scenes.length
      ? Math.round((completed / video.scenes.length) * 100)
      : 0,
  );
}

export function StoryLibrary() {
  const [videos, setVideos] = useState<GeneratedVideo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<StoryFilter>("all");
  const [sort, setSort] = useState<StorySort>("recent");
  const [pending, setPending] = useState<string | null>(null);

  async function refresh() {
    try {
      setVideos(await listGeneratedVideos());
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not load story projects",
      );
    }
  }

  useEffect(() => {
    let cancelled = false;
    void listGeneratedVideos()
      .then((items) => {
        if (!cancelled) {
          setVideos(items);
          setError(null);
        }
      })
      .catch((caught: Error) => {
        if (!cancelled) setError(caught.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!videos.some((video) => activeStatuses.has(video.status))) return;
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [videos]);

  const visibleVideos = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return videos
      .filter(
        (video) =>
          matchesFilter(video, filter) &&
          (!normalized ||
            video.plan.title.toLocaleLowerCase().includes(normalized) ||
            video.plan.logline.toLocaleLowerCase().includes(normalized) ||
            video.story.toLocaleLowerCase().includes(normalized)),
      )
      .toSorted((left, right) => {
        if (sort === "attention") {
          const priority = (video: GeneratedVideo) =>
            video.status === "failed"
              ? 2
              : activeStatuses.has(video.status)
                ? 1
                : 0;
          const difference = priority(right) - priority(left);
          if (difference) return difference;
        }
        const direction = sort === "oldest" ? 1 : -1;
        return (
          (new Date(left.created_at).getTime() -
            new Date(right.created_at).getTime()) *
          direction
        );
      });
  }, [filter, query, sort, videos]);

  const completed = videos.filter(
    (video) => video.status === "complete",
  ).length;
  const active = videos.filter((video) =>
    activeStatuses.has(video.status),
  ).length;
  const failed = videos.filter((video) => video.status === "failed").length;

  async function resume(video: GeneratedVideo) {
    setPending(video.id);
    try {
      const updated = await resumeGeneratedVideo(video.id);
      setVideos((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not resume story",
      );
    } finally {
      setPending(null);
    }
  }

  async function stop(video: GeneratedVideo) {
    setPending(video.id);
    try {
      const updated = await stopGeneratedVideo(video.id);
      setVideos((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not stop story",
      );
    } finally {
      setPending(null);
    }
  }

  async function remove(video: GeneratedVideo) {
    if (
      !window.confirm(`Delete “${video.plan.title}” and its generated files?`)
    )
      return;
    setPending(video.id);
    try {
      await deleteGeneratedVideo(video.id);
      setVideos((current) => current.filter((item) => item.id !== video.id));
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not delete story",
      );
    } finally {
      setPending(null);
    }
  }

  return (
    <main className="page story-library-page">
      <div className="topbar">
        <div>
          <span className="eyebrow">STORY STUDIO LIBRARY</span>
          <h1>Story projects</h1>
          <p>Manage every AI-directed film, render, and final master.</p>
        </div>
        <Link className="primary-link" href="/generate">
          ＋ Create story video
        </Link>
      </div>

      <section
        className="story-library-stats"
        aria-label="Story project summary"
      >
        <article>
          <span>Total stories</span>
          <strong>{videos.length}</strong>
        </article>
        <article>
          <span>Rendering</span>
          <strong>{active}</strong>
        </article>
        <article>
          <span>Masters ready</span>
          <strong>{completed}</strong>
        </article>
        <article className={failed ? "attention" : ""}>
          <span>Needs attention</span>
          <strong>{failed}</strong>
        </article>
      </section>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section className="section-block" aria-label="All story projects">
        <div className="project-browser-tools story-browser-tools">
          <label className="project-search">
            <span aria-hidden="true">⌕</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search stories"
              aria-label="Search stories"
            />
          </label>
          <div className="project-filters" aria-label="Filter stories">
            {(["all", "active", "complete", "failed"] as const).map(
              (option) => (
                <button
                  key={option}
                  type="button"
                  className={filter === option ? "active" : ""}
                  aria-pressed={filter === option}
                  onClick={() => setFilter(option)}
                >
                  {option}
                </button>
              ),
            )}
          </div>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as StorySort)}
            aria-label="Sort stories"
          >
            <option value="recent">Most recent</option>
            <option value="oldest">Oldest first</option>
            <option value="attention">Needs attention</option>
          </select>
        </div>

        {loading ? (
          <div className="loading-card">Loading story projects…</div>
        ) : videos.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon" aria-hidden="true">
              ✦
            </span>
            <h3>No story projects yet</h3>
            <p>
              Turn a prompt into your first locally generated character film.
            </p>
            <Link className="primary-link" href="/generate">
              Create your first story
            </Link>
          </div>
        ) : visibleVideos.length === 0 ? (
          <div className="empty-state compact">
            <h3>No matching stories</h3>
            <p>Try another search or status filter.</p>
          </div>
        ) : (
          <div className="story-project-grid">
            {visibleVideos.map((video) => {
              const progress = progressFor(video);
              const videoUrl = generatedVideoUrl(video);
              return (
                <article className="story-project-card" key={video.id}>
                  <Link
                    href={`/stories/${video.id}`}
                    className={`story-project-cover template-${video.template}`}
                    aria-label={`Open ${video.plan.title}`}
                  >
                    <span className={`status ${video.status}`}>
                      {video.status}
                    </span>
                    <div>
                      <strong>{video.aspect_ratio}</strong>
                      <small>
                        {video.quality} · {video.target_duration_seconds}s
                      </small>
                    </div>
                    {videoUrl ? (
                      <span className="story-play">▶</span>
                    ) : (
                      <b>{progress}%</b>
                    )}
                  </Link>
                  <div className="story-project-body">
                    <time dateTime={video.created_at}>
                      {new Intl.DateTimeFormat("en", {
                        dateStyle: "medium",
                        timeStyle: "short",
                      }).format(new Date(video.created_at))}
                    </time>
                    <h2>{video.plan.title}</h2>
                    <p>{video.plan.logline}</p>
                    <div className="story-project-phase">
                      <span>{video.phase}</span>
                      <strong>{progress}%</strong>
                    </div>
                    <div className="story-project-progress">
                      <i style={{ width: `${progress}%` }} />
                    </div>
                    <div className="story-project-actions">
                      <Link href={`/stories/${video.id}`}>Open project →</Link>
                      {["failed", "cancelled"].includes(video.status) && (
                        <button
                          type="button"
                          disabled={pending === video.id}
                          onClick={() => void resume(video)}
                        >
                          {pending === video.id
                            ? "Queueing recovery…"
                            : resumeSummary(video).label}
                        </button>
                      )}
                      {activeStatuses.has(video.status) && (
                        <button
                          type="button"
                          disabled={
                            pending === video.id ||
                            video.status === "cancel_requested"
                          }
                          onClick={() => void stop(video)}
                        >
                          {video.status === "cancel_requested"
                            ? "Stopping…"
                            : "Stop project"}
                        </button>
                      )}
                      {videoUrl && (
                        <a href={videoUrl} download>
                          Download
                        </a>
                      )}
                      {["failed", "complete", "cancelled"].includes(
                        video.status,
                      ) && (
                        <button
                          className="story-delete"
                          type="button"
                          disabled={pending === video.id}
                          aria-label={`Delete ${video.plan.title}`}
                          onClick={() => void remove(video)}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}

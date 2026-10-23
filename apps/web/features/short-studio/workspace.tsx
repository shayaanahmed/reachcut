"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { EpisodeReview } from "../content-series/episode-review";
import type { EpisodeDetail } from "../content-series/api";
import { request } from "../informative/api";
import type { Providers } from "../informative/api";
import { studioApi } from "./api";
import type { Category, StudioBrief, StudioJob } from "./api";
import { FrameLibrary } from "./frame-library";
import { FramePicker, defaultSelection } from "./frame-picker";
import type { FrameSelection } from "./frame-picker";
import { JobProgress } from "./job-progress";

export function ShortStudio() {
  const [category, setCategory] = useState<Category>("github");
  const [repoUrl, setRepoUrl] = useState("");
  const [context, setContext] = useState("");
  const [brief, setBrief] = useState<StudioBrief | null>(null);
  const [storyline, setStoryline] = useState("");
  const [selection, setSelection] = useState<FrameSelection>(defaultSelection);
  const [step, setStep] = useState(0);
  const [job, setJob] = useState<StudioJob | null>(null);
  const [jobId, setJobId] = useState("");
  const [detail, setDetail] = useState<EpisodeDetail | null>(null);
  const [providers, setProviders] = useState<Providers | null>(null);
  const [pending, setPending] = useState(false);
  const [pollVersion, setPollVersion] = useState(0);
  const [error, setError] = useState("");
  const ideaKey = useRef("");
  const planKey = useRef("");
  const generation = useRef(0);
  const resumeJob = useRef(false);
  const busy =
    pending ||
    Boolean(jobId && (!job || ["queued", "working"].includes(job.status)));
  useEffect(() => {
    let alive = true;
    const query = new URLSearchParams(window.location.search);
    void Promise.resolve().then(() => {
      if (!alive) return;
      if (query.get("sequence")) {
        const id = query.get("sequence")!;
        void studioApi
          .sequences()
          .then((items) => {
            const preset = items.find((s) => s.id === id);
            if (alive && preset)
              setSelection({
                mode: "manual",
                sequence: id,
                theme: query.get("theme") ?? "neon",
                frames: preset.frames,
              });
          })
          .catch((e: Error) => {
            if (alive) setError(e.message);
          });
      }
      if (!query.get("short") && !query.get("sequence")) {
        const saved = window.localStorage.getItem("reachcut-studio-job");
        if (saved) {
          resumeJob.current = true;
          setJobId(saved);
        }
      }
    });
    void request<Providers>("/shorts/providers")
      .then((p) => {
        if (alive) setProviders(p);
      })
      .catch(() => {});
    if (query.get("short"))
      void studioApi
        .episode(query.get("short")!)
        .then((d) => {
          if (alive) setDetail(d);
        })
        .catch((e: Error) => {
          if (alive) setError(e.message);
        });

    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    let restored = false;
    async function poll() {
      try {
        const current = await studioApi.job(jobId);
        if (!alive) return;
        setJob(current);
        setError("");
        if (
          resumeJob.current &&
          !restored &&
          current.brief &&
          current.storyboard_request
        ) {
          restored = true;
          setBrief(current.brief);
          setStoryline(current.storyboard_request.storyline_id);
          setStep(2);
          setSelection((previous) => ({
            ...previous,
            sequence: current.storyboard_request!.sequence_id,
            theme: current.storyboard_request!.theme ?? previous.theme,
            mode: current.storyboard_request!.frame_mode ?? "manual",
            frames: current.storyboard_request!.frames ?? previous.frames,
          }));
        }
        if (current.status === "ready") {
          if (current.brief) {
            setBrief(current.brief);
            setCategory(current.brief.category);
            setRepoUrl(current.brief.repo_url);
            setContext(current.brief.context);
            setStep(1);
          }
          if (current.storyboard_request) {
            setStoryline(current.storyboard_request.storyline_id);
            setSelection((previous) => ({
              ...previous,
              sequence: current.storyboard_request!.sequence_id,
              theme: current.storyboard_request!.theme ?? previous.theme,
              mode: current.storyboard_request!.frame_mode ?? "manual",
              frames: current.storyboard_request!.frames ?? previous.frames,
            }));
          }
          if (current.short_id) {
            const d = await studioApi.episode(current.short_id);
            if (!alive) return;
            setDetail(d);
            window.localStorage.removeItem("reachcut-studio-job");
            window.history.replaceState(
              null,
              "",
              `/create?short=${current.short_id}`,
            );
          }
        } else if (current.status !== "failed") timer = setTimeout(poll, 1600);
      } catch (e) {
        if (alive) {
          setError(
            e instanceof Error ? e.message : "Could not load Ollama progress",
          );
          timer = setTimeout(poll, 4000);
        }
      }
    }
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [jobId, pollVersion]);
  function reset(nextCategory: Category = category) {
    generation.current++;
    resumeJob.current = false;
    setCategory(nextCategory);
    setBrief(null);
    setStoryline("");
    setDetail(null);
    setJob(null);
    setJobId("");
    setError("");
    setPending(false);
    setStep(0);
    ideaKey.current = "";
    planKey.current = "";
    window.localStorage.removeItem("reachcut-studio-job");
    window.history.replaceState(null, "", "/create");
  }
  async function perform(operation: () => Promise<StudioJob>) {
    if (busy) return;
    const version = generation.current;
    setPending(true);
    setError("");
    try {
      const next = await operation();
      if (version !== generation.current) return;
      setJob(next);
      setJobId(next.id);
      setPollVersion((v) => v + 1);
      window.localStorage.setItem("reachcut-studio-job", next.id);
    } catch (e) {
      if (version === generation.current)
        setError(e instanceof Error ? e.message : "Could not start Ollama");
    } finally {
      if (version === generation.current) setPending(false);
    }
  }
  function findIdeas(regenerate = false) {
    if (regenerate) ideaKey.current = "";
    ideaKey.current ||= crypto.randomUUID();
    void perform(() =>
      studioApi.ideas({
        category,
        repo_url: category === "github" ? repoUrl.trim() : "",
        context,
        ...(category === "github" ? { flow: "storyboard" as const } : {}),
        previous_brief_id: regenerate ? (brief?.id ?? "") : "",
        request_key: ideaKey.current,
      }),
    );
  }
  function build() {
    if (!brief || !storyline) return;
    planKey.current ||= crypto.randomUUID();
    void perform(() =>
      studioApi.storyboard({
        brief_id: brief.id,
        storyline_id: storyline,
        sequence_id: selection.sequence,
        theme: selection.theme,
        frame_mode: brief.storyboard?.length ? "manual" : selection.mode,
        ...(selection.mode === "manual" && !brief.storyboard?.length
          ? { frames: selection.frames }
          : {}),
        auto_produce: Boolean(brief.storyboard?.length),
        request_key: planKey.current,
        feedback: "",
      }),
    );
  }
  const chosen = brief?.storylines.find((s) => s.id === storyline);
  const hasStoryboard = Boolean(brief?.storyboard?.length);
  const stepLabels =
    category === "github"
      ? [
          "Repository URL",
          "Review AI storyboard",
          "Choose template",
          "Create & refine video",
        ]
      : ["Start with an idea", "Pick a storyline", "Choose frames"];
  return (
    <main className="page short-studio-page">
      <div className="studio-page-heading">
        <div>
          <span className="eyebrow">REACHCUT · LOCAL OLLAMA</span>
          <h1>Create a short.</h1>
          <p>A useful discovery. A story worth watching.</p>
        </div>
        <div className="creation-actions">
          <Link href="/frames">Frame library</Link>
          <Link href="/created">Created videos</Link>
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {detail ? (
        <EpisodeReview
          key={
            detail.short.id +
            JSON.stringify(detail.short.script) +
            JSON.stringify(detail.short.settings)
          }
          detail={detail}
          onChange={setDetail}
          onStartOver={() => reset()}
          providers={providers}
          onRegenerate={(id) => {
            resumeJob.current = true;
            setDetail(null);
            setStep(2);
            window.history.replaceState(null, "", "/create");
            setJob(null);
            setJobId(id);
            window.localStorage.setItem("reachcut-studio-job", id);
          }}
        />
      ) : (
        <>
          <ol className="studio-progress" aria-label="Creation steps">
            {stepLabels.map((label, i) => (
              <li key={label} aria-current={step === i ? "step" : undefined}>
                <span>{i + 1}</span>
                {label}
              </li>
            ))}
          </ol>
          {busy && (
            <JobProgress
              kind={job?.kind ?? (step === 2 ? "storyboard" : "ideas")}
              phase={job?.phase ?? "Saving your task…"}
            />
          )}
          {job?.status === "failed" && (
            <div className="studio-error" role="alert">
              <strong>Ollama needs another try</strong>
              <p>{job.error}</p>
              <button
                disabled={pending}
                onClick={() =>
                  void perform(() =>
                    job.kind === "ideas" && job.ideas_request
                      ? studioApi.ideas(job.ideas_request)
                      : studioApi.storyboard(job.storyboard_request!),
                  )
                }
              >
                Retry saved task
              </button>
            </div>
          )}
          {step === 0 && (
            <section className="studio-input-panel">
              <h2>What are we sharing?</h2>
              <div className="studio-category-grid">
                <button
                  aria-pressed={category === "github"}
                  onClick={() => reset("github")}
                >
                  <span className="studio-category-icon">↗</span>
                  <strong>Exciting GitHub repos</strong>
                  <span>
                    One link. Discover what it does and why anyone should care.
                  </span>
                </button>
                <button
                  aria-pressed={category === "tech-tricks"}
                  onClick={() => reset("tech-tricks")}
                >
                  <span className="studio-category-icon">✦</span>
                  <strong>Tech tricks</strong>
                  <span>
                    Let Ollama find practical ideas worth trying and sharing.
                  </span>
                </button>
              </div>
              {category === "github" ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    findIdeas();
                  }}
                >
                  <label className="studio-url-label">
                    Public GitHub repo URL
                    <input
                      required
                      type="url"
                      placeholder="https://github.com/owner/repo"
                      value={repoUrl}
                      onChange={(e) => {
                        setRepoUrl(e.target.value);
                        ideaKey.current = "";
                      }}
                    />
                  </label>
                  <button
                    className="primary-button"
                    disabled={!repoUrl.trim()}
                    aria-disabled={busy}
                  >
                    {busy
                      ? "Writing your storyboard…"
                      : "Generate AI storyboard"}{" "}
                    <span aria-hidden="true">→</span>
                  </button>
                  <p className="studio-input-note">
                    Ollama reads the repo documentation and explores its purpose
                    and writes a catchy, factual storyboard before you choose a
                    template.
                  </p>
                </form>
              ) : (
                <div>
                  <details>
                    <summary>Anything in mind? (optional)</summary>
                    <label>
                      Focus for the ideas
                      <input
                        value={context}
                        maxLength={1000}
                        placeholder="e.g. browser shortcuts or everyday computer tips"
                        onChange={(e) => {
                          setContext(e.target.value);
                          ideaKey.current = "";
                        }}
                      />
                    </label>
                  </details>
                  <button
                    className="primary-button"
                    onClick={() => findIdeas()}
                  >
                    {busy
                      ? "Finding tech tricks…"
                      : "Find exciting tech tricks"}{" "}
                    <span aria-hidden="true">→</span>
                  </button>
                  <p className="studio-input-note">
                    Ollama develops ideas from official feature guides, with the
                    device and requirements included.
                  </p>
                </div>
              )}
            </section>
          )}
          {step === 1 && brief && hasStoryboard && (
            <section className="settings-card series-panel">
              <span className="eyebrow">{brief.subject} · AI STORYBOARD</span>
              <h2>Your repository storyboard</h2>
              <p>
                A curiosity hook, a concrete example and a clear payoff,
                grounded in the repository.
              </p>
              <ol className="series-storyboard">
                {brief.storyboard?.map((beat, index) => (
                  <li className="series-scene" key={index}>
                    <span className="eyebrow">
                      Scene {index + 1}
                      {index === 0
                        ? " · Hook"
                        : index === brief.storyboard!.length - 1
                          ? " · Closing"
                          : ""}
                    </span>
                    <h3>{beat.title}</h3>
                    <p>{beat.narration}</p>
                    <p>
                      <strong>On screen:</strong> {beat.caption}
                    </p>
                    <small>{beat.visual}</small>
                  </li>
                ))}
              </ol>
              {brief.storyboard_notes?.map((note, index) => (
                <p key={index}>{note}</p>
              ))}
              <div className="creation-actions">
                <button
                  className="primary-button"
                  disabled={busy}
                  onClick={() => {
                    setStoryline(
                      brief.storyboard_storyline_id ?? brief.storylines[0].id,
                    );
                    setSelection((previous) => ({
                      ...previous,
                      mode: "manual",
                    }));
                    planKey.current = "";
                    setStep(2);
                  }}
                >
                  Use storyboard → choose template
                </button>
                <button disabled={busy} onClick={() => findIdeas(true)}>
                  Rewrite storyboard with AI
                </button>
                <button onClick={() => reset()}>Change repository</button>
              </div>
              <details>
                <summary>Repository research</summary>
                <p>{brief.analysis}</p>
                {brief.sources.map((source) => (
                  <p key={source.id}>
                    <a href={source.url} target="_blank" rel="noreferrer">
                      {source.title}
                    </a>
                  </p>
                ))}
              </details>
            </section>
          )}
          {step === 1 && brief && !hasStoryboard && (
            <section>
              <div className="studio-section-heading">
                <div>
                  <span className="eyebrow">{brief.subject}</span>
                  <h2>Which story would you watch?</h2>
                  <p>
                    Choose a direction. Ollama will turn it into a complete
                    visual story.
                  </p>
                </div>
                <div className="studio-heading-actions">
                  <button
                    className="studio-secondary-button"
                    aria-disabled={busy}
                    onClick={() => findIdeas(true)}
                  >
                    Suggest different storylines
                  </button>
                  <button
                    className="studio-text-button"
                    onClick={() => reset()}
                  >
                    ← Change the starting idea
                  </button>
                </div>
              </div>
              <div className="studio-storyline-grid">
                {brief.storylines.map((story, i) => (
                  <button
                    className="studio-storyline-card"
                    key={story.id}
                    aria-pressed={storyline === story.id}
                    onClick={() => {
                      setStoryline(story.id);
                      planKey.current = "";
                      setStep(2);
                    }}
                  >
                    <div
                      className={`story-art story-art-${i % 3}`}
                      aria-hidden="true"
                    >
                      <span className="story-art-orbit" />
                      <span className="story-art-window">
                        <span className="story-art-dots">● ● ●</span>
                        <span className="story-art-icon">
                          {["⌘", "↗", "✦"][i % 3]}
                        </span>
                        <span className="story-art-lines">
                          <i />
                          <i />
                          <i />
                        </span>
                      </span>
                      <span className="story-art-label">
                        {["DISCOVER", "TRY IT", "IMAGINE"][i % 3]}
                      </span>
                    </div>
                    <span className="eyebrow">STORY 0{i + 1}</span>
                    <h3>{story.title}</h3>
                    <p className="studio-story-hook">“{story.hook}”</p>
                    <p>{story.focus}</p>
                    <div className="studio-payoff">
                      <strong>The payoff</strong>
                      <span>{story.payoff}</span>
                    </div>
                    {story.prerequisite && (
                      <p>
                        <strong>To try it:</strong> {story.prerequisite}
                      </p>
                    )}
                    <span className="studio-story-action">
                      Choose this story →
                    </span>
                  </button>
                ))}
              </div>
              <details className="studio-analysis">
                <summary>What Ollama learned</summary>
                <p>{brief.analysis}</p>
                {brief.sources.map((source) => (
                  <p key={source.id}>
                    <a href={source.url} target="_blank" rel="noreferrer">
                      {source.title}
                    </a>
                  </p>
                ))}
                {brief.notices.map((notice, i) => (
                  <p key={i}>{notice}</p>
                ))}
              </details>
            </section>
          )}
          {step === 2 && brief && (
            <section>
              <div className="studio-chosen-story">
                <span className="eyebrow">
                  {hasStoryboard
                    ? "YOUR APPROVED STORYBOARD"
                    : "YOUR STORYLINE"}
                </span>
                <h2>{chosen?.title}</h2>
                <p>{chosen?.hook}</p>
                <button
                  className="studio-secondary-button"
                  onClick={() => setStep(1)}
                >
                  {hasStoryboard ? "Review storyboard" : "Change storyline"}
                </button>
              </div>
              {hasStoryboard ? (
                <FrameLibrary
                  selected={selection.sequence}
                  sceneCount={brief.storyboard?.length}
                  onSelect={(id) => {
                    setSelection((previous) => ({
                      ...previous,
                      sequence: id,
                      mode: "manual",
                    }));
                    planKey.current = "";
                  }}
                />
              ) : (
                <FramePicker
                  value={selection}
                  onChange={(value) => {
                    setSelection(value);
                    planKey.current = "";
                  }}
                />
              )}
              <div className="studio-build-bar">
                <p>
                  {hasStoryboard
                    ? "Your saved storyboard is kept. We’ll render it with this template, then AI will inspect and refine the finished video."
                    : "Ollama writes the story into these frames. You can review or regenerate before making the video."}
                </p>
                <button
                  className="primary-button"
                  aria-disabled={busy}
                  onClick={build}
                >
                  {busy
                    ? hasStoryboard
                      ? "Preparing video…"
                      : "Building storyboard…"
                    : hasStoryboard
                      ? "Create video with this template →"
                      : "Build my storyboard →"}
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}

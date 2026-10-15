"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  GeneratedVideo,
  LocalVideoReadiness,
  StoryPlan,
  VideoGenerationTemplate,
  VideoTemplateId,
} from "../../lib/contracts";
import {
  stopGeneratedVideo,
  deleteStoryDraft,
  listStoryDrafts,
  saveStoryDraft,
  matchStoryFormat,
  type StoryDraft,
  type StoryDraftSettings,
  authorizeHuggingFace,
  createStoryIdea,
  downloadVideoModels,
  generateVideo,
  generatedVideoUrl,
  getVideoReadiness,
  listGeneratedVideos,
  listVideoTemplates,
  planStory,
  resumeGeneratedVideo,
  startVideoEngine,
  uploadStoryReference,
} from "./api";

import { resumeSummary } from "./resume-summary";
import { TemplateLibrary } from "./template-library";
import {
  resolveReferenceTemplate,
  type ReferenceSelection,
} from "./template-library-api";

const sampleStory =
  "A shy young clockmaker finds a mechanical bird that can rewind ten seconds. When a child drops a precious photograph into a storm drain, she must overcome her fear of the crowded city and use the bird's tiny power in a clever chain of attempts. End with the bird choosing to stay on her shoulder.";

type Duration = 10 | 15 | 20 | 30 | 45 | 60;

export function ShortsStudio() {
  const submitting = useRef(false);
  const creationController = useRef<AbortController | null>(null);
  const [drafts, setDrafts] = useState<StoryDraft[]>([]);
  const [editingDraft, setEditingDraft] = useState<string | null>(null);
  const [savedReference, setSavedReference] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [queueNotice, setQueueNotice] = useState<string | null>(null);
  const [templates, setTemplates] = useState<VideoGenerationTemplate[]>([]);
  const [videos, setVideos] = useState<GeneratedVideo[]>([]);
  const [readiness, setReadiness] = useState<LocalVideoReadiness | null>(null);
  const [selected, setSelected] = useState<VideoTemplateId | null>(null);
  const [referenceSelection, setReferenceSelection] =
    useState<ReferenceSelection>("none");
  const [matchReason, setMatchReason] = useState<string | null>(null);
  const [story, setStory] = useState("");
  const [plannedTemplate, setPlannedTemplate] =
    useState<VideoTemplateId>("cinematic_story");
  const [plan, setPlan] = useState<StoryPlan | null>(null);
  const [reference, setReference] = useState<File | null>(null);
  const [aspectRatio, setAspectRatio] = useState<"9:16" | "16:9" | "1:1">(
    "9:16",
  );
  const [quality, setQuality] = useState<"draft" | "1080p">("draft");
  const [duration, setDuration] = useState<Duration>(10);
  const [shotMode, setShotMode] = useState<"auto" | "continuous" | "story">(
    "auto",
  );
  const [narrationEnabled, setNarrationEnabled] = useState(false);
  const [activeVideo, setActiveVideo] = useState<GeneratedVideo | null>(null);
  const [busy, setBusy] = useState<
    "idea" | "plan" | "render" | "engine" | "auth" | "download" | "queue" | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === selected),
    [selected, templates],
  );

  useEffect(() => {
    void Promise.allSettled([
      listVideoTemplates(),
      listGeneratedVideos(),
      getVideoReadiness(),
      listStoryDrafts(),
    ]).then(([formats, generated, engine, queue]) => {
      if (formats.status === "fulfilled") setTemplates(formats.value);
      if (generated.status === "fulfilled") {
        setVideos(generated.value);
        setActiveVideo(generated.value[0] ?? null);
      }
      if (engine.status === "fulfilled") setReadiness(engine.value);
      if (queue.status === "fulfilled") setDrafts(queue.value);
      const failed = [formats, generated, engine, queue].find(
        (result) => result.status === "rejected",
      );
      if (failed?.status === "rejected")
        setError(
          failed.reason instanceof Error
            ? failed.reason.message
            : "Could not load studio",
        );
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (
      !videos.some((video) =>
        ["queued", "rendering", "finishing", "cancel_requested"].includes(
          video.status,
        ),
      )
    )
      return;
    const timer = window.setInterval(() => {
      void listGeneratedVideos()
        .then((updated) => {
          setVideos(updated);
          setActiveVideo(
            (current) =>
              updated.find((item) => item.id === current?.id) ?? current,
          );
        })
        .catch((caught: Error) =>
          setError(`Progress could not refresh: ${caught.message}`),
        );
    }, 2500);
    return () => window.clearInterval(timer);
  }, [videos]);

  useEffect(() => {
    if (!readiness || readiness.ready) return;
    const timer = window.setInterval(() => {
      void getVideoReadiness()
        .then(setReadiness)
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [readiness]);

  const processing = videos.some((video) =>
    ["queued", "rendering", "finishing", "cancel_requested"].includes(
      video.status,
    ),
  );

  async function resolveFormat(prompt: string, signal?: AbortSignal) {
    if (referenceSelection !== "none" && referenceSelection !== "auto")
      return resolveReferenceTemplate(referenceSelection, prompt);
    return matchStoryFormat(prompt, signal);
  }

  async function snapshot(): Promise<StoryDraftSettings> {
    const referenceId = reference
      ? await uploadStoryReference(reference)
      : savedReference;
    return {
      story: story.trim(),
      template: selected,
      aspect_ratio: aspectRatio,
      quality,
      target_duration_seconds: duration,
      shot_mode: shotMode,
      narration_enabled: narrationEnabled,
      ...(referenceId ? { reference_id: referenceId } : {}),
      ...(referenceSelection !== "none" && referenceSelection !== "auto"
        ? { reference_template_id: referenceSelection }
        : {}),
    };
  }

  async function enqueue() {
    if (story.trim().length < 20) {
      setError("Write at least 20 characters before adding a story.");
      return;
    }
    if (submitting.current) return;
    submitting.current = true;
    setBusy("queue");
    setError(null);
    try {
      const draft = await saveStoryDraft(
        await snapshot(),
        editingDraft ?? undefined,
      );
      setDrafts((current) =>
        editingDraft
          ? current.map((item) => (item.id === draft.id ? draft : item))
          : [...current, draft],
      );
      setEditingDraft(null);
      setStory("");
      setPlan(null);
      setReference(null);
      setSavedReference(undefined);
      setQueueNotice(
        "Story saved. Start the next short whenever you’re ready.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not save story",
      );
    } finally {
      submitting.current = false;
      setBusy(null);
    }
  }

  function editDraft(draft: StoryDraft) {
    const settings = draft.settings;
    setEditingDraft(draft.id);
    setStory(draft.story);
    setSelected(settings.template);
    setReferenceSelection(settings.reference_template_id ?? "none");
    setAspectRatio(settings.aspect_ratio);
    setQuality(settings.quality);
    setDuration(settings.target_duration_seconds);
    setShotMode(settings.shot_mode ?? "auto");
    setNarrationEnabled(settings.narration_enabled ?? false);
    setReference(null);
    setSavedReference(settings.reference_id);
    setPlan(null);
    setMatchReason(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function removeDraft(id: string) {
    setBusy("queue");
    setError(null);
    try {
      await deleteStoryDraft(id);
      setDrafts((current) => current.filter((item) => item.id !== id));
      if (editingDraft === id) setEditingDraft(null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not remove story",
      );
    } finally {
      setBusy(null);
    }
  }

  async function createShort(draft?: StoryDraft) {
    if (processing || submitting.current) return;
    if (!draft && story.trim().length < 20) {
      setError("Write at least 20 characters to create a short.");
      return;
    }
    submitting.current = true;
    setBusy("plan");
    setError(null);
    setQueueNotice(null);
    const controller = new AbortController();
    creationController.current = controller;
    try {
      const settings = draft ? draft.settings : await snapshot();
      controller.signal.throwIfAborted();
      const matched = settings.reference_template_id
        ? await resolveReferenceTemplate(
            settings.reference_template_id,
            settings.story,
          )
        : await matchStoryFormat(settings.story, controller.signal);
      controller.signal.throwIfAborted();
      const template =
        settings.template ?? matched?.template ?? "cinematic_story";
      if (matched) setMatchReason(matched.reason);
      const storyboard = await planStory(
        settings.story,
        {
          template,
          ...(settings.template ? { visual_style_override: true } : {}),
          aspect_ratio: settings.aspect_ratio,
          shot_mode: settings.shot_mode,
          narration_enabled: settings.narration_enabled,
          ...(matched?.reference_template_id
            ? { reference_template_id: matched.reference_template_id }
            : {}),
        },
        settings.target_duration_seconds,
        controller.signal,
      );
      controller.signal.throwIfAborted();
      setBusy("render");
      creationController.current = null;
      const generated = await generateVideo({
        story: settings.story,
        plan: storyboard,
        template,
        aspect_ratio: settings.aspect_ratio,
        quality: settings.quality,
        ...(settings.reference_id
          ? { reference_id: settings.reference_id }
          : {}),
        ...(draft ? { draft_id: draft.id } : {}),
      });
      setVideos((current) => [generated, ...current]);
      setActiveVideo(generated);
      if (draft)
        setDrafts((current) => current.filter((item) => item.id !== draft.id));
      setQueueNotice(
        "Short started. The next story stays queued until you start it.",
      );
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(
        caught instanceof Error
          ? caught.message
          : "Could not create short. Your queued story is saved.",
      );
    } finally {
      if (creationController.current === controller)
        creationController.current = null;
      submitting.current = false;
      setBusy(null);
    }
  }

  async function improveStory() {
    setBusy("idea");
    setError(null);
    const controller = new AbortController();
    creationController.current = controller;
    try {
      const matched = await resolveFormat(
        story.trim() || sampleStory,
        controller.signal,
      );
      controller.signal.throwIfAborted();
      if (matched) {
        setMatchReason(matched.reason);
      }
      const result = await createStoryIdea(
        story.trim() || sampleStory,
        selected ?? matched?.template ?? "cinematic_story",
        matched?.reference_template_id ?? undefined,
        selected !== null,
        controller.signal,
      );
      controller.signal.throwIfAborted();
      setStory(result.story);
      setPlan(null);
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(
        caught instanceof Error ? caught.message : "Story generation failed",
      );
    } finally {
      if (creationController.current === controller)
        creationController.current = null;
      setBusy(null);
    }
  }

  async function directStoryboard() {
    if (story.trim().length < 20) {
      setError(
        "Write at least a few sentences so the director can build real scenes.",
      );
      return;
    }
    setBusy("plan");
    setPlan(null);
    setError(null);
    const controller = new AbortController();
    creationController.current = controller;
    try {
      const matched = await resolveFormat(story.trim(), controller.signal);
      controller.signal.throwIfAborted();
      if (matched) {
        setMatchReason(matched.reason);
      }
      setPlannedTemplate(selected ?? matched?.template ?? "cinematic_story");
      const storyboard = await planStory(
        story.trim(),
        {
          template: selected ?? matched?.template ?? "cinematic_story",
          ...(selected ? { visual_style_override: true } : {}),
          aspect_ratio: aspectRatio,
          ...(shotMode !== "auto" ? { shot_mode: shotMode } : {}),
          ...(narrationEnabled ? { narration_enabled: true } : {}),
          ...(matched?.reference_template_id
            ? { reference_template_id: matched.reference_template_id }
            : {}),
        },
        duration,
        controller.signal,
      );
      controller.signal.throwIfAborted();
      setPlan(storyboard);
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(
        caught instanceof Error
          ? caught.message
          : "Storyboard generation failed",
      );
    } finally {
      if (creationController.current === controller)
        creationController.current = null;
      setBusy(null);
    }
  }

  function stopCreation() {
    creationController.current?.abort();
    setQueueNotice(
      "Story creation stopped. Your prompt and queued stories are saved.",
    );
  }

  async function stopRender(video: GeneratedVideo) {
    try {
      const updated = await stopGeneratedVideo(video.id);
      setVideos((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      setActiveVideo((current) =>
        current?.id === updated.id ? updated : current,
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not stop project",
      );
    }
  }

  async function startEngine() {
    setBusy("engine");
    setError(null);
    try {
      setReadiness(await startVideoEngine());
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Engine startup failed",
      );
    } finally {
      setBusy(null);
    }
  }

  async function authorizeModels() {
    setBusy("auth");
    setError(null);
    try {
      const authorizationUrl = await authorizeHuggingFace();
      window.open(authorizationUrl, "_blank", "noopener,noreferrer");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Authorization failed",
      );
    } finally {
      setBusy(null);
    }
  }

  async function downloadModels() {
    setBusy("download");
    setError(null);
    try {
      await downloadVideoModels();
      setReadiness(await getVideoReadiness());
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Model download failed",
      );
    } finally {
      setBusy(null);
    }
  }

  async function renderStory() {
    if (!plan || processing || submitting.current) return;
    submitting.current = true;
    setBusy("render");
    setError(null);
    try {
      const referenceId = reference
        ? await uploadStoryReference(reference)
        : savedReference;
      const generated = await generateVideo({
        story: story.trim(),
        plan,
        template: plannedTemplate,
        aspect_ratio: aspectRatio,
        quality,
        ...(referenceId ? { reference_id: referenceId } : {}),
      });
      setVideos((current) => [generated, ...current]);
      setActiveVideo(generated);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Video generation failed",
      );
    } finally {
      submitting.current = false;
      setBusy(null);
    }
  }

  async function resume(video: GeneratedVideo) {
    if (processing || submitting.current) return;
    setBusy("render");
    setError(null);
    try {
      const resumed = await resumeGeneratedVideo(video.id);
      setActiveVideo(resumed);
      setVideos((current) =>
        current.map((item) => (item.id === resumed.id ? resumed : item)),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Resume failed");
    } finally {
      setBusy(null);
    }
  }

  const activeUrl = activeVideo ? generatedVideoUrl(activeVideo) : null;

  return (
    <main className="page generation-page">
      <div className="topbar generation-topbar">
        <div>
          <span className="eyebrow">SHORTS STUDIO</span>
          <h1>Shorts Studio</h1>
          <p>
            Write your story, choose a format or let AI pick, and create a
            short.
          </p>
        </div>
        <div className="generation-topbar-actions">
          <Link href="/stories">Manage shorts →</Link>
          <div
            className={`generation-provider-note ${readiness?.ready ? "ready" : ""}`}
          >
            <span>
              {readiness?.ready ? "READY TO GENERATE" : "LOCAL ENGINE"}
            </span>
            <strong>{readiness?.engine_name ?? "Checking LTX 2.5…"}</strong>
            <small>
              {readiness?.detail ?? "Inspecting Ollama and model files"}
            </small>
          </div>
        </div>
      </div>

      {readiness && !readiness.ready && (
        <section
          className="engine-readiness"
          aria-label="Local engine readiness"
        >
          <div>
            <strong>One-time local setup</strong>
            <p>{readiness.detail}</p>
          </div>
          <div className="engine-checks">
            <span className={readiness.ollama_model_ready ? "ok" : ""}>
              Ollama model
            </span>
            <span className={readiness.engine_installed ? "ok" : ""}>
              LTX engine
            </span>
            <span className={readiness.models_ready ? "ok" : ""}>
              LTX weights
            </span>
          </div>
          {readiness.engine_installed && !readiness.engine_running && (
            <button
              type="button"
              onClick={() => void startEngine()}
              disabled={busy !== null}
            >
              {busy === "engine" ? "Starting…" : "Start local engine"}
            </button>
          )}
          {readiness.engine_running && !readiness.hf_authenticated && (
            <button
              type="button"
              onClick={() => void authorizeModels()}
              disabled={busy !== null}
            >
              {busy === "auth" ? "Opening…" : "Authorize model access"}
            </button>
          )}
          {readiness.engine_running &&
            readiness.hf_authenticated &&
            !readiness.models_ready &&
            readiness.download_status !== "downloading" && (
              <div className="engine-model-actions">
                <a
                  href="https://huggingface.co/Lightricks/LTX-2.5"
                  target="_blank"
                  rel="noreferrer"
                >
                  Accept LTX license
                </a>
                <button
                  type="button"
                  onClick={() => void downloadModels()}
                  disabled={busy !== null}
                >
                  {busy === "download"
                    ? "Starting…"
                    : "Download LTX 2.5 models"}
                </button>
              </div>
            )}
          {readiness.download_status === "downloading" && (
            <strong>
              {Math.round(
                Math.min(1, Math.max(0, readiness.download_progress)) * 100,
              )}
              %
            </strong>
          )}
        </section>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {loading && (
        <p className="loading-card" role="status">
          Loading your studio and saved queue…
        </p>
      )}
      {busy && (
        <div className="studio-wait" role="status" aria-live="polite">
          <span className="studio-spinner" aria-hidden="true" />
          <div>
            <strong>
              {busy === "plan"
                ? "Choosing direction and planning your scenes…"
                : busy === "render"
                  ? "Sending your short to the renderer…"
                  : busy === "queue"
                    ? "Saving your queue…"
                    : "Working on your request…"}
            </strong>
            <p>
              {busy === "plan"
                ? "This can take a few minutes. Your queued stories stay saved if processing fails."
                : "You can follow render progress below."}
            </p>
          </div>
        </div>
      )}
      {(busy === "idea" || busy === "plan") && (
        <button type="button" onClick={stopCreation}>
          Stop story creation
        </button>
      )}
      {queueNotice && <p role="status">{queueNotice}</p>}
      {matchReason && <p role="status">Template match: {matchReason}</p>}

      <div className="generation-layout">
        <section
          className="generation-builder"
          aria-label="Story video generator"
        >
          <fieldset
            className="studio-fields"
            disabled={busy !== null || loading}
          >
            <div className="generation-step-heading">
              <span>01</span>
              <div>
                <h2>Video format</h2>
                <p>
                  Choose a video template, or just write your story and let AI
                  find the best format.
                </p>
              </div>
            </div>
            <TemplateLibrary
              selection={referenceSelection}
              disabled={busy !== null}
              onSelect={(value) => {
                setReferenceSelection(value);
                setPlan(null);
                setMatchReason(null);
              }}
            />
            <details
              className="studio-details"
              open={selected !== null || undefined}
            >
              <summary>
                Optional visual style
                {selectedTemplate ? ` · ${selectedTemplate.name}` : ""}
              </summary>
              <p>
                Keep the video template’s style, or choose an optional look such
                as Cinematic or Animated.
              </p>
              <button
                type="button"
                className={`studio-auto ${selected === null ? "active" : ""}`}
                aria-pressed={selected === null}
                onClick={() => {
                  setSelected(null);
                  setPlan(null);
                  setMatchReason(null);
                }}
              >
                Use the video template’s style
              </button>
              <div className="generation-template-grid">
                {templates.map((template) => (
                  <button
                    type="button"
                    key={template.id}
                    className={template.id === selected ? "active" : ""}
                    aria-pressed={template.id === selected}
                    onClick={() => {
                      setSelected(template.id);
                      setMatchReason(null);
                      setPlan(null);
                    }}
                  >
                    <span
                      className="generation-template-art"
                      style={{
                        background: `linear-gradient(145deg, #${template.palette[0]}, #${template.palette[1]})`,
                      }}
                    >
                      <b>{template.badge}</b>
                      <i
                        style={{ backgroundColor: `#${template.palette[2]}` }}
                      />
                    </span>
                    <strong>{template.name}</strong>
                    <small>{template.description}</small>
                  </button>
                ))}
              </div>
            </details>

            <div className="generation-divider" />
            <div className="generation-step-heading">
              <span>02</span>
              <div>
                <h2>Tell your story</h2>
                <p>
                  {referenceSelection === "none"
                    ? (selectedTemplate?.prompt_hint ??
                      "Describe the characters and what happens.")
                    : "Describe the action, lighting and camera you want."}
                </p>
              </div>
            </div>
            <label className="generation-prompt story-prompt">
              <textarea
                value={story}
                maxLength={8000}
                onChange={(event) => {
                  setStory(event.target.value);
                  setMatchReason(null);
                  setPlan(null);
                }}
                placeholder={sampleStory}
                aria-label="Story"
              />
              <span>{story.length} / 8000</span>
            </label>
            <div className="prompt-tools">
              <button
                type="button"
                className="ai-prompt-button"
                onClick={() => void improveStory()}
                disabled={busy !== null}
              >
                <span aria-hidden="true">✦</span>
                {busy === "idea"
                  ? "Writing with Ollama…"
                  : "Turn my idea into a viral story"}
              </button>
              <small>
                You can also paste a complete story or an AI-written prompt
                here.
              </small>
            </div>

            <div className="generation-settings" aria-label="Story settings">
              <label>
                Format
                <select
                  value={aspectRatio}
                  onChange={(event) => {
                    setAspectRatio(event.target.value as typeof aspectRatio);
                    setPlan(null);
                  }}
                >
                  <option value="9:16">9:16 · Shorts</option>
                  <option value="16:9">16:9 · Film</option>
                  <option value="1:1">1:1 · Square</option>
                </select>
              </label>
              <label>
                Story length
                <select
                  value={duration}
                  onChange={(event) => {
                    setDuration(Number(event.target.value) as Duration);
                    setPlan(null);
                  }}
                >
                  <option value={10}>10 seconds</option>
                  <option value={20}>20 seconds</option>
                  <option value={30}>30 seconds</option>
                  <option value={45}>45 seconds</option>
                  <option value={60}>60 seconds</option>
                </select>
              </label>
              <label>
                Render
                <select
                  value={quality}
                  onChange={(event) =>
                    setQuality(event.target.value as typeof quality)
                  }
                >
                  <option value="draft">Draft · 540p</option>
                  <option value="1080p">Final · 1080p</option>
                </select>
              </label>
            </div>
            <details className="studio-details">
              <summary>
                Advanced settings · narration and reference image
              </summary>
              <div className="generation-settings">
                <label>
                  Shot structure
                  <select
                    value={shotMode}
                    disabled={busy !== null}
                    onChange={(event) => {
                      setShotMode(event.target.value as typeof shotMode);
                      setPlan(null);
                    }}
                  >
                    <option value="auto">Auto · match the format</option>
                    <option value="continuous">
                      Continuous action · fewer cuts
                    </option>
                    <option value="story">Story scenes</option>
                  </select>
                </label>
                <label>
                  Spoken narration
                  <select
                    value={narrationEnabled ? "on" : "off"}
                    disabled={busy !== null}
                    onChange={(event) => {
                      setNarrationEnabled(event.target.value === "on");
                      setPlan(null);
                    }}
                  >
                    <option value="off">Off · natural sound</option>
                    <option value="on">On · narrator</option>
                  </select>
                </label>
              </div>
              <label className="character-reference-input">
                <span>
                  <strong>Opening frame or character reference</strong>
                  <small>
                    Optional — upload a starting composition or character image
                    to anchor the first shot.
                  </small>
                </span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(event) => {
                    setReference(event.target.files?.[0] ?? null);
                    setSavedReference(undefined);
                  }}
                />
                <b>{reference ? reference.name : "Choose image"}</b>
              </label>
            </details>
            <div className="studio-create-actions">
              <button
                type="button"
                className="generation-submit"
                disabled={
                  busy !== null ||
                  !readiness?.ready ||
                  processing ||
                  editingDraft !== null
                }
                onClick={() => void createShort()}
              >
                Create short
              </button>
              <button
                type="button"
                className="generation-submit secondary"
                onClick={() => void enqueue()}
              >
                {editingDraft ? "Save queued story" : "Add to queue"}
              </button>
              {editingDraft && (
                <button
                  type="button"
                  onClick={() => {
                    setEditingDraft(null);
                    setStory("");
                    setPlan(null);
                    setSavedReference(undefined);
                  }}
                >
                  Cancel edit
                </button>
              )}
            </div>
            {processing && (
              <p role="status">
                A short is processing. Add more stories to the queue while you
                wait.
              </p>
            )}
            {!readiness?.ready && (
              <p className="generation-disclosure">
                You can save stories now. Finish engine setup to start creating
                shorts.
              </p>
            )}
            <details className="studio-details">
              <summary>Review a storyboard before creating</summary>
              <button
                type="button"
                className="generation-submit secondary"
                onClick={() => void directStoryboard()}
                disabled={busy !== null}
              >
                {busy === "plan"
                  ? "Directing scenes…"
                  : plan
                    ? "Redraft storyboard"
                    : "Create storyboard"}
              </button>

              {plan && (
                <section
                  className="storyboard-review"
                  aria-label="Storyboard review"
                >
                  <header>
                    <div>
                      <span className="eyebrow">OLLAMA STORYBOARD</span>
                      <h3>{plan.title}</h3>
                      <p>{plan.logline}</p>
                    </div>
                    <span>{plan.scenes.length} scenes</span>
                  </header>
                  {plan.characters.length > 0 && (
                    <div className="character-bible">
                      {plan.characters.map((character) => (
                        <article key={character.id}>
                          <strong>{character.name}</strong>
                          <small>{character.role}</small>
                          <p>{character.appearance_anchor}</p>
                        </article>
                      ))}
                    </div>
                  )}
                  <div className="storyboard-scenes">
                    {plan.scenes.map((scene) => (
                      <article key={scene.index}>
                        <span>{String(scene.index).padStart(2, "0")}</span>
                        <div>
                          <strong>{scene.title}</strong>
                          <p>{scene.story_beat}</p>
                          <small>
                            {scene.camera_motion.replaceAll("_", " ")} ·{" "}
                            {scene.duration_seconds}s
                          </small>
                        </div>
                      </article>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="generation-submit"
                    onClick={() => void renderStory()}
                    disabled={busy !== null || !readiness?.ready || processing}
                  >
                    <span aria-hidden="true">▶</span>
                    {busy === "render"
                      ? "Queueing local render…"
                      : `Generate ${quality === "1080p" ? "1080p" : "draft"} story video`}
                  </button>
                  {!readiness?.ready && (
                    <p className="generation-disclosure">
                      Finish the local engine checks above before GPU rendering.
                    </p>
                  )}
                </section>
              )}
            </details>
          </fieldset>
        </section>

        <aside
          className="generation-preview"
          aria-label="Generated video preview"
        >
          <header>
            <div>
              <span className="eyebrow">LOCAL RENDER</span>
              <h2>{activeVideo?.plan.title ?? "Your film appears here"}</h2>
            </div>
            {activeVideo && (
              <span className="quality-badge">{activeVideo.quality}</span>
            )}
          </header>
          <div
            className={`generation-player ratio-${(activeVideo?.aspect_ratio ?? aspectRatio).replace(":", "-")}`}
          >
            {activeUrl ? (
              <video
                key={activeVideo?.id}
                src={activeUrl}
                controls
                playsInline
                aria-label="Generated story video"
              />
            ) : activeVideo ? (
              <div className="generation-progress-card">
                <span>{Math.round(activeVideo.progress * 100)}%</span>
                <strong>{activeVideo.phase}</strong>
                <div>
                  <i style={{ width: `${activeVideo.progress * 100}%` }} />
                </div>
                <ol>
                  {activeVideo.scenes.map((scene) => (
                    <li key={scene.id} className={scene.status}>
                      <span>{scene.scene_index}</span>
                      <small>{scene.title}</small>
                      <b>{scene.status}</b>
                    </li>
                  ))}
                </ol>
                {[
                  "queued",
                  "rendering",
                  "finishing",
                  "cancel_requested",
                ].includes(activeVideo.status) && (
                  <button
                    type="button"
                    disabled={activeVideo.status === "cancel_requested"}
                    onClick={() => void stopRender(activeVideo)}
                  >
                    {activeVideo.status === "cancel_requested"
                      ? "Stopping…"
                      : "Stop project"}
                  </button>
                )}
                {activeVideo.status === "cancelled" && (
                  <Link href={`/stories/${activeVideo.id}`}>
                    Resume or delete project
                  </Link>
                )}
                {(activeVideo.status === "failed" ||
                  activeVideo.status === "queued") && (
                  <button
                    type="button"
                    onClick={() => void resume(activeVideo)}
                  >
                    {activeVideo.status === "queued"
                      ? "Retry queued render"
                      : busy === "render"
                        ? "Queueing recovery…"
                        : resumeSummary(activeVideo).label}
                  </button>
                )}
                {activeVideo.status === "failed" && (
                  <p>{resumeSummary(activeVideo).detail}</p>
                )}
                {activeVideo.error && (
                  <small className="generation-job-error">
                    {activeVideo.error}
                  </small>
                )}
              </div>
            ) : (
              <div className="generation-placeholder">
                <span>✦</span>
                <strong>Story-driven character video</strong>
                <small>
                  Write a story and create your short. Follow each scene as it
                  renders here.
                </small>
              </div>
            )}
          </div>
          {activeVideo && (
            <div className="generation-result-meta">
              <div>
                <strong>
                  {activeVideo.status === "complete"
                    ? "Master ready"
                    : activeVideo.status}
                </strong>
                <small>
                  {activeVideo.target_duration_seconds}s ·{" "}
                  {activeVideo.aspect_ratio} · {activeVideo.provider}
                </small>
              </div>
              {activeUrl && (
                <a href={activeUrl} download>
                  Download MP4
                </a>
              )}
            </div>
          )}
          <section className="studio-queue" aria-label="Manual story queue">
            <header>
              <h3>Story queue ({drafts.length})</h3>
            </header>
            <p>Stories run one at a time. You start each short manually.</p>
            <button
              type="button"
              disabled={
                loading ||
                editingDraft !== null ||
                busy !== null ||
                processing ||
                !readiness?.ready ||
                drafts.length === 0
              }
              onClick={() => void createShort(drafts[0])}
            >
              Start next short
            </button>
            {drafts.length === 0 ? (
              <p>No stories waiting. Add a story to build your queue.</p>
            ) : (
              <ol>
                {drafts.map((draft) => (
                  <li key={draft.id}>
                    <strong>
                      {draft.story.slice(0, 90)}
                      {draft.story.length > 90 ? "…" : ""}
                    </strong>
                    <small>
                      {draft.settings.template?.replaceAll("_", " ") ??
                        "AI chooses format"}{" "}
                      · {draft.settings.target_duration_seconds}s ·{" "}
                      {draft.settings.quality}
                    </small>
                    <div>
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => editDraft(draft)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        disabled={busy !== null}
                        aria-label={`Remove queued story ${draft.story.slice(0, 30)}`}
                        onClick={() => void removeDraft(draft.id)}
                      >
                        Remove
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
          {activeVideo && (
            <Link className="primary-link" href={`/stories/${activeVideo.id}`}>
              {activeVideo.status === "complete"
                ? "Manage & share short →"
                : "Open short →"}
            </Link>
          )}
          {videos.length > 0 && (
            <div className="generation-history">
              <h3>Story projects</h3>
              {videos.slice(0, 6).map((video) => (
                <button
                  key={video.id}
                  type="button"
                  className={video.id === activeVideo?.id ? "active" : ""}
                  onClick={() => setActiveVideo(video)}
                >
                  <span>▶</span>
                  <span>
                    <strong>{video.plan.title}</strong>
                    <small>
                      {video.status} · {video.target_duration_seconds}s
                    </small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </aside>
      </div>
    </main>
  );
}

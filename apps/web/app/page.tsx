"use client";

import { useEffect, useState } from "react";
import {
  listProjects,
  previewUrl,
  processProject,
  renderClip,
  setApproval,
  uploadProject,
} from "../lib/api";
import type { Project } from "../lib/contracts";

const STAGE_ORDER = [
  "probe",
  "transcribe",
  "select_candidates",
  "render_previews",
] as const;

const STAGE_LABELS: Record<(typeof STAGE_ORDER)[number], string> = {
  probe: "Inspect media",
  transcribe: "Transcribe locally",
  select_candidates: "Find highlights",
  render_previews: "Render previews",
};

function projectProgress(project: Project): number {
  const progress = STAGE_ORDER.reduce((total, name) => {
    const stage = project.stages.find((item) => item.name === name);
    if (stage?.status === "succeeded") return total + 1;
    if (stage?.status === "running") return total + stage.progress;
    return total;
  }, 0);
  return progress / STAGE_ORDER.length;
}

function errorMessage(error: Record<string, unknown> | null): string | null {
  return typeof error?.message === "string" ? error.message : null;
}

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasProcessingProjects = projects.some(
    (project) => project.status === "processing",
  );

  useEffect(() => {
    void listProjects()
      .then(setProjects)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!hasProcessingProjects) return;
    let active = true;
    const refresh = () => {
      void listProjects()
        .then((updated) => {
          if (active) setProjects(updated);
        })
        .catch((e: Error) => {
          if (active) setError(e.message);
        });
    };
    refresh();
    const timer = window.setInterval(refresh, 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [hasProcessingProjects]);

  async function upload(formData: FormData) {
    setBusy(true);
    setError(null);
    try {
      const created = await uploadProject(formData);
      setProjects((current) => [created, ...current]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function process(id: string) {
    setBusy(true);
    setError(null);
    try {
      await processProject(id);
      setProjects((items) =>
        items.map((item) =>
          item.id === id ? { ...item, status: "processing" } : item,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Processing failed");
    } finally {
      setBusy(false);
    }
  }

  async function approve(clipId: string, approved: boolean) {
    try {
      const updated = await setApproval(clipId, approved);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approval failed");
    }
  }

  async function render(clipId: string) {
    setBusy(true);
    try {
      await renderClip(clipId);
      setProjects(await listProjects());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Render failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header>
        <span className="eyebrow">LOCAL VIDEO WORKBENCH</span>
        <h1>
          Find the moment.
          <br />
          Keep the meaning.
        </h1>
        <p>
          Private transcription and editorial selection, with you making the
          final call.
        </p>
      </header>
      <section className="panel" aria-labelledby="new-project">
        <h2 id="new-project">New project</h2>
        <form action={upload}>
          <label>
            Project name
            <input
              name="title"
              required
              maxLength={200}
              placeholder="Founder interview — August"
            />
          </label>
          <label>
            Source video
            <input name="media" type="file" accept="video/*,.mkv" required />
          </label>
          <label className="check">
            <input
              name="authorization_confirmed"
              type="checkbox"
              value="true"
              required
            />
            <span>
              I own, license, or have permission to repurpose this media.
            </span>
          </label>
          <button disabled={busy}>
            {busy ? "Working…" : "Import locally"}
          </button>
        </form>
        <p className="notice">
          A public link does not grant publication rights. Files remain in your
          configured local data directory.
        </p>
      </section>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <section aria-labelledby="projects">
        <div className="section-title">
          <h2 id="projects">Projects</h2>
          <span>{projects.length} LOCAL</span>
        </div>
        <div className="projects">
          {projects.length === 0 ? (
            <p className="empty">No media imported yet.</p>
          ) : (
            projects.map((project) => (
              <article className="project" key={project.id}>
                <div>
                  <span className={`status ${project.status}`}>
                    {project.status}
                  </span>
                  <h3>{project.title}</h3>
                  <p>
                    {project.original_filename}
                    {project.duration_seconds
                      ? ` · ${Math.round(project.duration_seconds)}s`
                      : ""}
                  </p>
                </div>
                {["created", "failed"].includes(project.status) && (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => void process(project.id)}
                  >
                    {project.status === "failed" ? "Retry analysis" : "Analyze"}
                  </button>
                )}
                {project.stages.length > 0 && (
                  <div className="pipeline" aria-label="Analysis progress">
                    <div className="pipeline-summary">
                      <strong>
                        {project.status === "failed"
                          ? "Analysis needs attention"
                          : project.status === "review"
                            ? "Analysis complete"
                            : "Analyzing locally"}
                      </strong>
                      <span>{Math.round(projectProgress(project) * 100)}%</span>
                    </div>
                    <progress max={1} value={projectProgress(project)} />
                    <div className="stage-list">
                      {STAGE_ORDER.map((name) => {
                        const stage = project.stages.find(
                          (item) => item.name === name,
                        );
                        const stageError = errorMessage(stage?.error ?? null);
                        return (
                          <div
                            className={`stage ${stage?.status ?? "pending"}`}
                            key={name}
                          >
                            <span className="stage-dot" aria-hidden="true" />
                            <div>
                              <strong>{STAGE_LABELS[name]}</strong>
                              <small>
                                {stage?.status === "running"
                                  ? `${Math.round(stage.progress * 100)}% · attempt ${stage.attempts}`
                                  : stage?.status === "failed"
                                    ? `Failed · attempt ${stage.attempts}`
                                    : stage?.status === "succeeded"
                                      ? "Complete"
                                      : "Waiting"}
                              </small>
                              {stageError && <p role="alert">{stageError}</p>}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                {project.clips.length > 0 && (
                  <div className="clips">
                    {project.clips.map((clip, index) => (
                      <div className="clip" key={clip.id}>
                        {clip.preview_path && (
                          <video
                            className="preview"
                            src={previewUrl(clip.id)}
                            controls
                            preload="metadata"
                            aria-label={`Preview ${index + 1}`}
                          />
                        )}
                        <div className="score">{clip.plan.scores.overall}</div>
                        <div>
                          <strong>
                            {clip.plan.hook?.text ?? `Candidate ${index + 1}`}
                          </strong>
                          <p>{clip.plan.rationale}</p>
                          <small>
                            {clip.plan.source.start_seconds.toFixed(1)}–
                            {clip.plan.source.end_seconds.toFixed(1)}s ·
                            editorial heuristic
                          </small>
                        </div>
                        <div className="actions">
                          <button
                            className="approve"
                            onClick={() => void approve(clip.id, true)}
                          >
                            Approve
                          </button>
                          <button
                            className="reject"
                            onClick={() => void approve(clip.id, false)}
                          >
                            Reject
                          </button>
                          {clip.approval_status === "approved" && (
                            <button
                              className="secondary"
                              disabled={busy}
                              onClick={() => void render(clip.id)}
                            >
                              Render final
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            ))
          )}
        </div>
      </section>
    </main>
  );
}

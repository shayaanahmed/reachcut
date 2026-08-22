"use client";

import { useEffect, useState } from "react";
import {
  getProject,
  listProjects,
  previewUrl,
  processProject,
  renderClip,
  setApproval,
  uploadProject,
} from "../lib/api";
import type { Project } from "../lib/contracts";

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void listProjects()
      .then(setProjects)
      .catch((e: Error) => setError(e.message));
  }, []);

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
      for (let attempt = 0; attempt < 900; attempt += 1) {
        const updated = await getProject(id);
        setProjects((items) =>
          items.map((item) => (item.id === updated.id ? updated : item)),
        );
        if (["review", "failed"].includes(updated.status)) break;
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
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
                {project.status !== "review" && (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => void process(project.id)}
                  >
                    Analyze
                  </button>
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

"use client";

import { useEffect, useState } from "react";
import type { Project } from "../../lib/contracts";
import { ActionLink } from "../../components/action-link";
import {
  loadWorkflows,
  retryWorkflow,
  startWorkflow,
  type WorkflowKind,
  type WorkflowState,
} from "./workflow-api";

const choices: { id: WorkflowKind; label: string; description: string }[] = [
  {
    id: "clips",
    label: "Generate clips",
    description:
      "Create a new set of clips. Existing edits and posts stay with their current output.",
  },
  {
    id: "full",
    label: "Prepare full video",
    description:
      "Publish the entire source without clipping. Create a separate master and publishing draft.",
  },
  {
    id: "metadata",
    label: "Refresh publishing details",
    description:
      "Refresh titles, descriptions and hashtags for selected existing clips. Video files and live posts are preserved.",
  },
  {
    id: "language",
    label: "Create language version",
    description:
      "Create an independent language version with its own review, publishing destinations and posts.",
  },
];
export function SourceWorkflows({
  project,
  onChanged,
}: {
  project: Project;
  onChanged: () => void;
}) {
  const [kind, setKind] = useState<WorkflowKind>("clips");
  const [clipIds, setClipIds] = useState<string[]>([]);
  const [language, setLanguage] = useState("ar");
  const [scopes, setScopes] = useState<string[]>(["metadata"]);
  const [audio, setAudio] = useState<File>();
  const [state, setState] = useState<WorkflowState>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [requestId, setRequestId] = useState<string>();
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const result = await loadWorkflows(project.id);
        if (!active) return;
        setState(result);
        if (result.speech_available === false)
          setScopes((current) =>
            current.filter((item) => item !== "subtitles"),
          );
        if (
          result.runs.some((run) => ["queued", "running"].includes(run.status))
        )
          timer = setTimeout(() => void refresh(), 4000);
      } catch (caught) {
        if (active)
          setError(
            caught instanceof Error
              ? caught.message
              : "Could not load workflows",
          );
      }
    }
    void refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [project.id, project.status, reload]);
  const active = [
    "queued",
    "processing",
    "downloading",
    "cancel_requested",
  ].includes(project.status);
  const parent = state?.runs.find(
    (run) =>
      run.target_project_id === project.id &&
      run.source_project_id !== project.id,
  );
  const selected = choices.find((choice) => choice.id === kind)!;
  function toggleScope(scope: string) {
    setRequestId(undefined);
    setScopes((current) =>
      current.includes(scope)
        ? current.filter((item) => item !== scope)
        : [...current, scope],
    );
  }
  return (
    <section className="source-workflows" aria-label="Source video workflows">
      {parent?.source_project_id && (
        <ActionLink href={`/projects/${parent.source_project_id}`} icon="←">
          Source: {parent.source_title}
        </ActionLink>
      )}
      <div className="section-heading">
        <div>
          <span className="eyebrow">ONE SOURCE · MULTIPLE OUTPUTS</span>
          <h2>What would you like to create?</h2>
        </div>
      </div>
      <div
        className="workflow-choices"
        role="tablist"
        aria-label="Source workflow"
      >
        {choices.map((choice) => (
          <button
            key={choice.id}
            type="button"
            role="tab"
            aria-selected={kind === choice.id}
            onClick={() => {
              setKind(choice.id);
              setRequestId(undefined);
            }}
          >
            <strong>{choice.label}</strong>
          </button>
        ))}
      </div>
      <form
        className="workflow-options"
        role="tabpanel"
        aria-label={selected.label}
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          setNotice("");
          const id = requestId ?? crypto.randomUUID();
          setRequestId(id);
          try {
            const run = await startWorkflow(
              project.id,
              {
                idempotency_key: id,
                kind,
                clip_ids: ["metadata", "language"].includes(kind)
                  ? clipIds
                  : [],
                target_language: kind === "language" ? language : undefined,
                scopes: kind === "language" ? scopes : ["metadata"],
              },
              scopes.includes("narration") && kind === "language"
                ? audio
                : undefined,
            );
            setNotice(
              `Workflow queued. ${run.target_project_id === project.id ? "Existing drafts will refresh." : "Open its independent output in the run history below."}`,
            );
            setReload((value) => value + 1);
            setRequestId(undefined);
            onChanged();
          } catch (caught) {
            setError(
              caught instanceof Error
                ? caught.message
                : "Workflow could not start",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <p>{selected.description}</p>
        {["metadata", "language"].includes(kind) &&
          project.clips.length > 0 && (
            <fieldset>
              <legend>
                {kind === "metadata"
                  ? "Existing clips to refresh"
                  : "Clips to create language versions from"}
              </legend>
              <small>No selection means all existing clips.</small>
              {project.clips.map((clip, index) => (
                <label key={clip.id}>
                  <input
                    type="checkbox"
                    checked={clipIds.includes(clip.id)}
                    onChange={(event) => {
                      setRequestId(undefined);
                      setClipIds((current) =>
                        event.target.checked
                          ? [...current, clip.id]
                          : current.filter((id) => id !== clip.id),
                      );
                    }}
                  />
                  {clip.plan.suggested_title || `Clip ${index + 1}`}
                </label>
              ))}
            </fieldset>
          )}
        {kind === "metadata" && !project.clips.length && (
          <p role="status">Create clips or prepare the full video first.</p>
        )}
        {kind === "language" && (
          <>
            <label>
              Target language
              <select
                value={language}
                onChange={(event) => {
                  setLanguage(event.target.value);
                  setRequestId(undefined);
                }}
              >
                {[
                  ["ar", "Arabic"],
                  ["ur", "Urdu"],
                  ["vi", "Vietnamese"],
                  ["en", "English"],
                  ["es", "Spanish"],
                  ["fr", "French"],
                  ["de", "German"],
                  ["hi", "Hindi"],
                ].map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <fieldset>
              <legend>What should be translated?</legend>
              <label>
                <input
                  type="checkbox"
                  checked={scopes.includes("metadata")}
                  onChange={() => toggleScope("metadata")}
                />
                Publishing titles, descriptions & hashtags
              </label>
              <label>
                <input
                  type="checkbox"
                  disabled={state?.speech_available === false}
                  checked={scopes.includes("subtitles")}
                  onChange={() => toggleScope("subtitles")}
                />
                Spoken subtitles
              </label>
              {state?.speech_available === false && (
                <small>
                  No spoken transcript was detected. Embedded video text remains
                  unchanged.
                </small>
              )}
              <label>
                <input
                  type="checkbox"
                  checked={scopes.includes("narration")}
                  onChange={() => toggleScope("narration")}
                />
                Replace narration with uploaded translated audio
              </label>
            </fieldset>
            {scopes.includes("narration") && (
              <label>
                Translated narration
                <input
                  type="file"
                  accept="audio/*"
                  required
                  onChange={(event) => {
                    setAudio(event.target.files?.[0]);
                    setRequestId(undefined);
                  }}
                />
                <small>
                  Select one clip and upload audio no longer than the video, and
                  at most two seconds shorter. This replaces original audio; it
                  does not generate a cloned voice.
                </small>
              </label>
            )}
            <p className="muted">
              Metadata-only translation keeps the video. Subtitle or narration
              changes create a reviewable preview; approve and render it before
              publishing. Text already baked into frames is retained.
            </p>
          </>
        )}
        {active && (
          <p role="status">
            This output already has a pipeline running. Wait for completion
            before starting another workflow.
          </p>
        )}
        <button
          className="primary-button"
          disabled={
            busy ||
            active ||
            (kind === "metadata" && !project.clips.length) ||
            (kind === "language" && !scopes.length)
          }
        >
          {busy ? "Starting workflow…" : selected.label}
        </button>
      </form>
      {error && (
        <p role="alert" className="error">
          {error}{" "}
          <button onClick={() => setReload((value) => value + 1)}>
            Reload workflows
          </button>
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <details className="workflow-history" open>
        <summary>Workflow runs & outputs ({state?.runs.length ?? 0})</summary>
        {!state?.runs.length && (
          <p>
            No workflow runs yet. Your current clips remain available below.
          </p>
        )}
        {state?.runs.map((run) => (
          <article key={run.id}>
            <div>
              <strong>
                {choices.find((choice) => choice.id === run.kind)?.label}
                {run.target_language ? ` · ${run.target_language}` : ""}
              </strong>
              <small>
                {new Date(run.created_at).toLocaleString()} ·{" "}
                {run.scopes.join(", ")}
              </small>
            </div>
            <span className="post-state">{run.status}</span>
            <ActionLink href={`/projects/${run.target_project_id}`}>
              Open output
            </ActionLink>
            {["failed", "cancelled"].includes(run.status) && (
              <button
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await retryWorkflow(run.id);
                    setReload((value) => value + 1);
                    onChanged();
                  } catch (caught) {
                    setError(
                      caught instanceof Error ? caught.message : "Retry failed",
                    );
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Retry this run
              </button>
            )}
            {run.error && (
              <p className="error" role="alert">
                {run.error}
              </p>
            )}
          </article>
        ))}
      </details>
    </section>
  );
}

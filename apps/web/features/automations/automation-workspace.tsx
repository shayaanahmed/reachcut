"use client";

import { useEffect, useMemo, useState } from "react";

import type {
  AutomationPipeline,
  ClipType,
  Project,
  SocialAccount,
} from "../../lib/contracts";
import { listProjects, stopProject, retryProject } from "../projects/api";
import { ProjectQueue, projectPhase } from "../projects/project-queue";
import { ProjectSource } from "./project-source";
import { listSocialAccounts } from "../publishing/api";
import {
  createAutomation,
  deleteAutomation,
  listAutomations,
  runAutomation,
  setAutomationActive,
} from "./api";

const clipTypes: { value: ClipType; label: string }[] = [
  { value: "funny", label: "Funny" },
  { value: "advice", label: "Advice" },
  { value: "insight", label: "Insight" },
  { value: "story", label: "Story" },
  { value: "debate", label: "Debate" },
  { value: "educational", label: "Educational" },
  { value: "emotional", label: "Emotional" },
  { value: "promotional", label: "Promotional" },
];

type BuilderDraft = {
  name: string;
  projectId: string;
  accountIds: string[];
  clipSelection: "all" | "best";
  clipTypes: ClipType[];
  schedule: "once" | "daily" | "weekly";
  nextRunAt: string;
  titleTemplate: string;
  descriptionTemplate: string;
};

const emptyDraft: BuilderDraft = {
  name: "",
  projectId: "",
  accountIds: [],
  clipSelection: "best",
  clipTypes: [],
  schedule: "once",
  nextRunAt: "",
  titleTemplate: "{clip_title}",
  descriptionTemplate: "{hashtags}",
};

export function AutomationWorkspace() {
  const [automations, setAutomations] = useState<AutomationPipeline[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [draft, setDraft] = useState<BuilderDraft>(emptyDraft);
  const [activeStep, setActiveStep] = useState(0);
  const [creating, setCreating] = useState(false);
  const [pendingProject, setPendingProject] = useState<string | null>(null);
  const [pendingPipeline, setPendingPipeline] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const projectNames = useMemo(
    () => new Map(projects.map((project) => [project.id, project.title])),
    [projects],
  );

  async function refresh() {
    const [pipelines, projectItems, accountItems] = await Promise.all([
      listAutomations(),
      listProjects(),
      listSocialAccounts(),
    ]);
    setAutomations(pipelines);
    setProjects(projectItems);
    setAccounts(
      accountItems.filter(
        (account) =>
          account.is_active && account.connection_status === "connected",
      ),
    );
  }

  useEffect(() => {
    void Promise.all([listAutomations(), listProjects(), listSocialAccounts()])
      .then(([pipelines, projectItems, accountItems]) => {
        setAutomations(pipelines);
        setProjects(projectItems);
        setAccounts(
          accountItems.filter(
            (account) =>
              account.is_active && account.connection_status === "connected",
          ),
        );
      })
      .catch((caught: Error) => setError(caught.message));
    const timer = window.setInterval(() => {
      void Promise.all([listAutomations(), listProjects()])
        .then(([pipelines, items]) => {
          setAutomations(pipelines);
          setProjects(items);
        })
        .catch((caught: Error) => setError(caught.message));
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const steps = [
    {
      title: "Source",
      caption: draft.projectId
        ? (projectNames.get(draft.projectId) ?? "Selected project")
        : "Choose a project",
      complete: Boolean(draft.projectId),
    },
    {
      title: "Clip logic",
      caption:
        draft.clipTypes.length > 0
          ? `${draft.clipTypes.length} moment type${draft.clipTypes.length === 1 ? "" : "s"}`
          : "Any strong moment",
      complete: true,
    },
    {
      title: "Publish",
      caption:
        draft.accountIds.length > 0
          ? `${draft.accountIds.length} destination${draft.accountIds.length === 1 ? "" : "s"}`
          : "Choose destinations",
      complete: draft.accountIds.length > 0,
    },
    {
      title: "Schedule",
      caption: draft.nextRunAt
        ? scheduleLabel(draft.schedule)
        : "Set launch time",
      complete: Boolean(draft.name.trim() && draft.nextRunAt),
    },
  ];

  function advance() {
    if (activeStep === 0 && !draft.projectId) {
      setError("Choose a source project before continuing.");
      return;
    }
    if (activeStep === 2 && draft.accountIds.length === 0) {
      setError("Choose at least one publishing destination.");
      return;
    }
    setError(null);
    setActiveStep((current) => Math.min(current + 1, steps.length - 1));
  }

  async function createPipeline() {
    if (!draft.projectId || draft.accountIds.length === 0) {
      setError("Complete the source and destination steps first.");
      return;
    }
    if (!draft.name.trim() || !draft.nextRunAt) {
      setError("Give the pipeline a name and first run time.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await createAutomation({
        name: draft.name.trim(),
        project_id: draft.projectId,
        social_account_ids: draft.accountIds,
        clip_selection: draft.clipSelection,
        clip_types: draft.clipTypes,
        schedule: draft.schedule,
        next_run_at: new Date(draft.nextRunAt).toISOString(),
        title_template: draft.titleTemplate,
        description_template: draft.descriptionTemplate,
      });
      setDraft(emptyDraft);
      setActiveStep(0);
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not create pipeline",
      );
    } finally {
      setCreating(false);
    }
  }

  async function updatePipeline(id: string, action: () => Promise<unknown>) {
    setPendingPipeline(id);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Pipeline update failed",
      );
    } finally {
      setPendingPipeline(null);
    }
  }

  async function updateProjectQueue(id: string, action: () => Promise<void>) {
    setPendingProject(id);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Could not update queue",
      );
    } finally {
      setPendingProject(null);
    }
  }

  return (
    <main className="page automations-page">
      <div className="topbar automation-topbar">
        <div>
          <span className="eyebrow">AUTOPILOT</span>
          <h1>Your content, on autopilot</h1>
          <p>
            Add a video, choose the moments that matter, and let your publishing
            flow take it from there.
          </p>
        </div>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="automation-overview" aria-label="Automation overview">
        <div>
          <span>Scheduled & active</span>
          <strong>
            {automations.filter((p) => p.status === "active").length}
          </strong>
          <small>Ready for their next run</small>
        </div>
        <div>
          <span>Projects in progress</span>
          <strong>
            {
              projects.filter((p) =>
                [
                  "queued",
                  "downloading",
                  "processing",
                  "cancel_requested",
                ].includes(p.status),
              ).length
            }
          </strong>
          <small>Processing in the background</small>
        </div>
        <div>
          <span>Needs attention</span>
          <strong>
            {automations.filter((p) => p.status === "failed").length +
              projects.filter((p) => p.status === "failed").length}
          </strong>
          <small>Open a failed item to retry</small>
        </div>
      </div>
      <ProjectQueue
        projects={projects}
        pendingId={pendingProject}
        onCancel={(id) => updateProjectQueue(id, () => stopProject(id))}
        onRetry={(id) => updateProjectQueue(id, () => retryProject(id))}
      />
      <section className="automation-grid">
        <section
          className="pipeline-builder"
          aria-labelledby="pipeline-builder-title"
        >
          <div className="pipeline-builder-heading">
            <div>
              <span className="eyebrow">NEW PIPELINE</span>
              <h2 id="pipeline-builder-title">Build the flow</h2>
            </div>
            <span className="pipeline-step-count">{activeStep + 1} / 4</span>
          </div>

          <nav className="pipeline-flow" aria-label="Pipeline builder steps">
            {steps.map((step, index) => (
              <div className="pipeline-flow-segment" key={step.title}>
                {index > 0 && (
                  <span className="pipeline-connector" aria-hidden="true">
                    →
                  </span>
                )}
                <button
                  type="button"
                  className={`pipeline-node ${activeStep === index ? "active" : ""} ${step.complete ? "complete" : ""}`}
                  aria-current={activeStep === index ? "step" : undefined}
                  onClick={() => {
                    setError(null);
                    setActiveStep(index);
                  }}
                >
                  <span className="pipeline-node-icon" aria-hidden="true">
                    {step.complete ? "✓" : index + 1}
                  </span>
                  <span>
                    <strong>{step.title}</strong>
                    <small>{step.caption}</small>
                  </span>
                </button>
              </div>
            ))}
          </nav>

          <div className="pipeline-stage">
            {activeStep === 0 && (
              <div className="pipeline-stage-content">
                <div>
                  <span className="stage-number">01</span>
                  <h3>Pick the video project</h3>
                  <p>
                    Choose a project or add a new video without leaving this
                    flow.
                  </p>
                </div>
                <ProjectSource
                  projects={projects}
                  selectedId={draft.projectId}
                  onSelect={(projectId) =>
                    setDraft((current) => ({ ...current, projectId }))
                  }
                  onCreated={(project) => {
                    setProjects((current) => [
                      project,
                      ...current.filter((item) => item.id !== project.id),
                    ]);
                    setDraft((current) => ({
                      ...current,
                      projectId: project.id,
                    }));
                  }}
                />
              </div>
            )}

            {activeStep === 1 && (
              <div className="pipeline-stage-content">
                <div>
                  <span className="stage-number">02</span>
                  <h3>Define what gets clipped</h3>
                  <p>
                    Choose the volume and the kinds of moments this flow should
                    look for.
                  </p>
                </div>
                <div
                  className="choice-cards two-column"
                  role="group"
                  aria-label="Clip volume"
                >
                  {(["best", "all"] as const).map((selection) => (
                    <button
                      type="button"
                      key={selection}
                      className={
                        draft.clipSelection === selection ? "selected" : ""
                      }
                      onClick={() =>
                        setDraft({ ...draft, clipSelection: selection })
                      }
                    >
                      <strong>
                        {selection === "best" ? "Best clip" : "All matches"}
                      </strong>
                      <small>
                        {selection === "best"
                          ? "Publish only the highest-scored result"
                          : "Publish every clip matching these rules"}
                      </small>
                    </button>
                  ))}
                </div>
                <fieldset className="pipeline-options">
                  <legend>
                    Moment types <span>optional</span>
                  </legend>
                  <div className="moment-chip-grid">
                    {clipTypes.map((type) => {
                      const selected = draft.clipTypes.includes(type.value);
                      return (
                        <button
                          type="button"
                          key={type.value}
                          className={selected ? "selected" : ""}
                          aria-pressed={selected}
                          onClick={() =>
                            setDraft({
                              ...draft,
                              clipTypes: selected
                                ? draft.clipTypes.filter(
                                    (item) => item !== type.value,
                                  )
                                : [...draft.clipTypes, type.value],
                            })
                          }
                        >
                          {type.label}
                        </button>
                      );
                    })}
                  </div>
                  <small>
                    No selection lets ReachCut discover any high-signal moment.
                  </small>
                </fieldset>
              </div>
            )}

            {activeStep === 2 && (
              <div className="pipeline-stage-content">
                <div>
                  <span className="stage-number">03</span>
                  <h3>Connect publishing destinations</h3>
                  <p>
                    Select every connected account that should receive clips
                    from this flow.
                  </p>
                </div>
                {accounts.length === 0 ? (
                  <div className="empty-state compact">
                    <h3>No connected accounts</h3>
                    <p>
                      Connect and activate a social account before creating a
                      pipeline.
                    </p>
                  </div>
                ) : (
                  <div className="destination-grid">
                    {accounts.map((account) => {
                      const selected = draft.accountIds.includes(account.id);
                      return (
                        <button
                          type="button"
                          key={account.id}
                          className={selected ? "selected" : ""}
                          aria-pressed={selected}
                          onClick={() =>
                            setDraft({
                              ...draft,
                              accountIds: selected
                                ? draft.accountIds.filter(
                                    (id) => id !== account.id,
                                  )
                                : [...draft.accountIds, account.id],
                            })
                          }
                        >
                          <span className="destination-mark">
                            {account.platform.charAt(0).toUpperCase()}
                          </span>
                          <span>
                            <strong>{account.label}</strong>
                            <small>{account.platform}</small>
                          </span>
                          <b aria-hidden="true">{selected ? "✓" : "+"}</b>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {activeStep === 3 && (
              <div className="pipeline-stage-content">
                <div>
                  <span className="stage-number">04</span>
                  <h3>Name and launch the flow</h3>
                  <p>
                    Set the first run and whether ReachCut should repeat it.
                  </p>
                </div>
                <label>
                  Pipeline name
                  <input
                    maxLength={120}
                    value={draft.name}
                    onChange={(event) =>
                      setDraft({ ...draft, name: event.target.value })
                    }
                    placeholder="Daily podcast highlights"
                  />
                </label>
                <div className="schedule-row">
                  <label>
                    First run
                    <input
                      type="datetime-local"
                      value={draft.nextRunAt}
                      onChange={(event) =>
                        setDraft({ ...draft, nextRunAt: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Repeat
                    <select
                      value={draft.schedule}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          schedule: event.target
                            .value as BuilderDraft["schedule"],
                        })
                      }
                    >
                      <option value="once">Once</option>
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                    </select>
                  </label>
                </div>
                <details className="pipeline-advanced">
                  <summary>Post templates</summary>
                  <div>
                    <label>
                      Post title
                      <input
                        value={draft.titleTemplate}
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            titleTemplate: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      Description
                      <textarea
                        rows={3}
                        value={draft.descriptionTemplate}
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            descriptionTemplate: event.target.value,
                          })
                        }
                      />
                    </label>
                    <small>
                      Variables: {"{clip_title}"}, {"{project_title}"},{" "}
                      {"{clip_type}"}, {"{hashtags}"}
                    </small>
                  </div>
                </details>
              </div>
            )}
          </div>

          <div className="pipeline-builder-actions">
            <button
              type="button"
              className="secondary"
              disabled={activeStep === 0 || creating}
              onClick={() =>
                setActiveStep((current) => Math.max(0, current - 1))
              }
            >
              Back
            </button>
            {activeStep < steps.length - 1 ? (
              <button
                type="button"
                className="primary-button"
                onClick={advance}
              >
                Continue →
              </button>
            ) : (
              <button
                type="button"
                className="primary-button"
                disabled={creating || accounts.length === 0}
                onClick={() => void createPipeline()}
              >
                {creating ? "Creating…" : "Activate pipeline"}
              </button>
            )}
          </div>
        </section>

        <section
          className="automation-list"
          aria-labelledby="scheduled-pipelines"
        >
          <div className="automation-list-heading">
            <div>
              <span className="eyebrow">YOUR FLOWS</span>
              <h2 id="scheduled-pipelines">Pipeline control</h2>
            </div>
            <span>{automations.length} total</span>
          </div>
          {automations.length === 0 ? (
            <div className="empty-state compact">
              <h3>No pipelines yet</h3>
              <p>
                Build the connected flow on the left to automate distribution.
              </p>
            </div>
          ) : (
            automations.map((pipeline) => {
              const enabled = ["active", "running"].includes(pipeline.status);
              const pending = pendingPipeline === pipeline.id;
              const source = projects.find((p) => p.id === pipeline.project_id);
              const waiting =
                pipeline.status === "active" &&
                source &&
                [
                  "queued",
                  "processing",
                  "downloading",
                  "cancel_requested",
                ].includes(source.status);
              const displayStatus = waiting
                ? "waiting for source"
                : pipeline.status === "active"
                  ? "scheduled"
                  : pipeline.status;
              return (
                <article
                  key={pipeline.id}
                  className={`automation-card ${enabled ? "enabled" : "disabled"}`}
                >
                  <header>
                    <div>
                      <span className={`status ${pipeline.status}`}>
                        {displayStatus}
                      </span>
                      <h3>{pipeline.name}</h3>
                    </div>
                    <div className="pipeline-toggle-wrap">
                      <span>{enabled ? "Active" : "Inactive"}</span>
                      <button
                        type="button"
                        role="switch"
                        aria-label={`${enabled ? "Deactivate" : "Activate"} ${pipeline.name}`}
                        aria-checked={enabled}
                        className={`pipeline-switch ${enabled ? "on" : ""}`}
                        disabled={pending || pipeline.status === "running"}
                        onClick={() =>
                          void updatePipeline(pipeline.id, () =>
                            setAutomationActive(pipeline.id, !enabled),
                          )
                        }
                      >
                        <span />
                      </button>
                    </div>
                  </header>
                  {source && (
                    <p className="automation-source-status">
                      <span className={`status ${source.status}`}>
                        {source.status}
                      </span>
                      {projectPhase(source)}
                    </p>
                  )}
                  <div
                    className="automation-mini-flow"
                    aria-label="Pipeline summary"
                  >
                    <span>
                      <small>Source</small>
                      <strong>
                        {projectNames.get(pipeline.project_id) ?? "Project"}
                      </strong>
                    </span>
                    <i aria-hidden="true">→</i>
                    <span>
                      <small>Clip</small>
                      <strong>
                        {pipeline.clip_selection === "best"
                          ? "Best match"
                          : "All matches"}
                      </strong>
                    </span>
                    <i aria-hidden="true">→</i>
                    <span>
                      <small>Publish</small>
                      <strong>
                        {pipeline.social_account_ids
                          .map(
                            (id) =>
                              accounts.find((account) => account.id === id)
                                ?.label ?? "Account",
                          )
                          .join(", ")}
                      </strong>
                    </span>
                  </div>
                  <div className="automation-timing">
                    <span>
                      <small>Next run</small>
                      <strong>
                        {pipeline.status === "completed"
                          ? "Completed"
                          : new Date(pipeline.next_run_at).toLocaleString()}
                      </strong>
                    </span>
                    <span>
                      <small>Frequency</small>
                      <strong>{scheduleLabel(pipeline.schedule)}</strong>
                    </span>
                  </div>
                  {pipeline.clip_types.length > 0 && (
                    <div className="pipeline-tags">
                      {pipeline.clip_types.map((type) => (
                        <span key={type}>{type}</span>
                      ))}
                    </div>
                  )}
                  {pipeline.last_error && (
                    <p className="error">{pipeline.last_error}</p>
                  )}
                  <div className="automation-actions">
                    <button
                      type="button"
                      className="secondary"
                      disabled={pending || pipeline.status === "running"}
                      onClick={() =>
                        void updatePipeline(pipeline.id, () =>
                          runAutomation(pipeline.id),
                        )
                      }
                    >
                      {pipeline.status === "running"
                        ? "Running…"
                        : pipeline.status === "failed"
                          ? "Retry run"
                          : "Run now"}
                    </button>
                    <button
                      type="button"
                      className="danger-button"
                      disabled={pending || pipeline.status === "running"}
                      onClick={() => {
                        if (window.confirm(`Delete “${pipeline.name}”?`))
                          void updatePipeline(pipeline.id, () =>
                            deleteAutomation(pipeline.id),
                          );
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </article>
              );
            })
          )}
        </section>
      </section>
    </main>
  );
}

function scheduleLabel(schedule: AutomationPipeline["schedule"]) {
  if (schedule === "daily") return "Every day";
  if (schedule === "weekly") return "Every week";
  return "One time";
}

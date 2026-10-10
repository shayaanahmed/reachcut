"use client";

import { useEffect, useRef, useState } from "react";

import {
  analyzeClipTracking,
  deleteClipSecondaryMedia,
  renderClip,
  setApproval,
  translateClip,
  updateClipStyle,
  uploadClipSecondaryMedia,
  type ClipStyleUpdate,
} from "../clips/api";
import type {
  ClipType,
  ClipTypeSuggestion,
  Project,
  SocialAccount,
} from "../../lib/contracts";
import {
  addMetricSnapshot,
  createPublication,
  deletePublication,
  listSocialAccounts,
  refreshPublication,
  syncMetricSnapshot,
  type MetricCreate,
  type PublicationCreate,
} from "../publishing/api";
import {
  deleteProject,
  getClipTypeSuggestions,
  getProject,
  importProjectUrl,
  listProjects,
  processProject,
  updateProject,
  uploadProject,
  type UrlImportRequest,
} from "./api";

type Clip = Project["clips"][number];
export type OperationState = "queued" | "working";

export function updateClipApproval(
  projects: Project[],
  clipId: string,
  approvalStatus: string,
): Project[] {
  return projects.map((project) => ({
    ...project,
    clips: project.clips.map((clip) =>
      clip.id === clipId ? { ...clip, approval_status: approvalStatus } : clip,
    ),
  }));
}

function sourceSlices(value: FormDataEntryValue | null) {
  const slices = String(value ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const [start, end, extra] = part.split("-").map((item) => item.trim());
      const startSeconds = Number(start);
      const endSeconds = Number(end);
      if (
        extra !== undefined ||
        !Number.isFinite(startSeconds) ||
        !Number.isFinite(endSeconds) ||
        endSeconds <= startSeconds
      ) {
        throw new Error(`Invalid source slice “${part}”; use start-end`);
      }
      return { start_seconds: startSeconds, end_seconds: endSeconds };
    });
  if (slices.length === 0)
    throw new Error("At least one source slice is required");
  return slices;
}

function styleUpdate(form: HTMLFormElement, clip: Clip): ClipStyleUpdate {
  const data = new FormData(form);
  const override = String(data.get("caption_text_override") ?? "").trim();
  const effects = clip.plan.effects.filter(
    (effect) =>
      ![
        "punch_zoom",
        "slow_zoom",
        "progress_bar",
        "question_card",
        "quote_card",
        "speaker_label",
      ].includes(effect.type),
  );
  if (data.get("zoom_effect") !== "none") {
    effects.push({
      time_seconds: 1,
      type: data.get("zoom_effect") as "punch_zoom" | "slow_zoom",
      parameters: {
        scale: data.get("zoom_effect") === "punch_zoom" ? 1.14 : 1.08,
        duration_seconds: data.get("zoom_effect") === "punch_zoom" ? 0.6 : 5,
      },
    });
  }
  if (data.get("progress_bar") === "true")
    effects.push({ time_seconds: 0, type: "progress_bar", parameters: {} });
  const cardText = String(data.get("card_text") ?? "").trim();
  if (cardText)
    effects.push({
      time_seconds: Number(data.get("card_time_seconds")),
      type: data.get("card_type") as
        "question_card" | "quote_card" | "speaker_label",
      parameters: {
        text: cardText,
        duration_seconds: Number(data.get("card_duration_seconds")),
      },
    });
  return {
    frame_style: data.get("frame_style") as Clip["plan"]["frame_style"],
    crop_focus_x: Number(data.get("crop_focus_x")),
    crop_focus_y: Number(data.get("crop_focus_y")),
    source_slices: sourceSlices(data.get("source_slices")),
    hook_text: String(data.get("hook_text") ?? "").trim() || undefined,
    hook_render: data.get("hook_render") === "true",
    content_mode: data.get("content_mode") as Clip["plan"]["content_mode"],
    enhancement_level: data.get(
      "enhancement_level",
    ) as Clip["plan"]["enhancement_level"],
    tracking_enabled: data.get("tracking_enabled") === "true",
    tracking_strategy: data.get(
      "tracking_strategy",
    ) as Clip["plan"]["tracking"]["strategy"],
    transition_style: data.get(
      "transition_style",
    ) as Clip["plan"]["transition_style"],
    transition_duration_seconds: Number(
      data.get("transition_duration_seconds"),
    ),
    cta_text: String(data.get("cta_text") ?? "").trim() || undefined,
    cta_render: data.get("cta_render") === "true",
    cta_style: data.get("cta_style") as NonNullable<
      Clip["plan"]["cta"]
    >["style"],
    effects,
    audio_track_index: Number(data.get("audio_track_index")),
    caption_config: {
      preset: data.get(
        "caption_preset",
      ) as Clip["plan"]["caption_config"]["preset"],
      enabled: data.get("captions_enabled") === "true",
      position: data.get(
        "position",
      ) as Clip["plan"]["caption_config"]["position"],
      animation: data.get(
        "animation",
      ) as Clip["plan"]["caption_config"]["animation"],
      font_family: String(data.get("font_family")),
      font_size: Number(data.get("font_size")),
      max_words_per_line: Number(data.get("max_words_per_line")),
      text_color: String(data.get("text_color")).toUpperCase(),
      highlight_color: String(data.get("highlight_color")).toUpperCase(),
      outline_color: String(data.get("outline_color")).toUpperCase(),
      highlighted_words: String(data.get("highlighted_words"))
        .split(",")
        .map((word) => word.trim())
        .filter(Boolean),
      text_override: override || null,
      source_language: clip.plan.caption_config.source_language,
      target_language: clip.plan.caption_config.target_language,
      translation_mode: clip.plan.caption_config.translation_mode,
      translated_text: clip.plan.caption_config.translated_text,
    },
  };
}

export function useProjectWorkbench(
  projectId?: string,
  options: { loadProjects?: boolean; loadAccounts?: boolean } = {},
) {
  const loadProjects = options.loadProjects ?? true;
  const loadAccounts = options.loadAccounts ?? false;
  const [projects, setProjects] = useState<Project[]>([]);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [operations, setOperations] = useState<Record<string, OperationState>>(
    {},
  );
  const [loading, setLoading] = useState(loadProjects);
  const [error, setError] = useState<string | null>(null);
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const [clipTypes, setClipTypes] = useState<Record<string, ClipType[]>>({});
  const [clipTypeSuggestions, setClipTypeSuggestions] = useState<
    Record<string, ClipTypeSuggestion[]>
  >({});
  const renderQueue = useRef<Promise<void>>(Promise.resolve());
  const busy = Object.keys(operations).length > 0;
  const hasProcessingProjects = projects.some(
    (project) => project.status === "processing",
  );
  const processingPublicationKey = projects
    .flatMap((project) =>
      project.clips.flatMap((clip) =>
        clip.publications
          .filter((publication) => publication.status === "processing")
          .map((publication) => publication.id),
      ),
    )
    .join(",");
  const metricsPublicationKey = projects
    .flatMap((project) =>
      project.clips.flatMap((clip) =>
        clip.publications
          .filter(
            (publication) =>
              publication.status === "published" &&
              publication.platform === "youtube" &&
              publication.social_account_id,
          )
          .map((publication) => publication.id),
      ),
    )
    .join(",");

  useEffect(() => {
    if (!loadProjects) return;
    const load = projectId
      ? getProject(projectId).then((project) => [project])
      : listProjects();
    void load
      .then(setProjects)
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, [loadProjects, projectId]);

  const reviewedProjectKey = projects
    .filter((project) => project.status === "review")
    .map((project) => project.id)
    .join(",");

  useEffect(() => {
    if (!reviewedProjectKey) return;
    const ids = reviewedProjectKey.split(",");
    void Promise.all(
      ids.map(async (id) => [id, await getClipTypeSuggestions(id)] as const),
    )
      .then((items) => setClipTypeSuggestions(Object.fromEntries(items)))
      .catch((caught: Error) => setError(caught.message));
  }, [reviewedProjectKey]);

  useEffect(() => {
    if (!loadAccounts) return;
    void listSocialAccounts()
      .then(setAccounts)
      .catch((caught: Error) => setError(caught.message));
  }, [loadAccounts]);

  useEffect(() => {
    if (!hasProcessingProjects) return;
    let active = true;
    const refresh = () => {
      const load = projectId
        ? getProject(projectId).then((project) => [project])
        : listProjects();
      void load
        .then((updated) => {
          if (active) setProjects(updated);
        })
        .catch((caught: Error) => {
          if (active) setError(caught.message);
        });
    };
    refresh();
    const timer = window.setInterval(refresh, 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [hasProcessingProjects, projectId]);

  useEffect(() => {
    if (!processingPublicationKey) return;
    let active = true;
    const publicationIds = processingPublicationKey.split(",");
    const refresh = () => {
      void Promise.all(publicationIds.map(refreshPublication))
        .then((updatedProjects) => {
          if (!active) return;
          const latest = new Map(
            updatedProjects.map((project) => [project.id, project]),
          );
          setProjects((items) =>
            items.map((project) => latest.get(project.id) ?? project),
          );
        })
        .catch((caught: Error) => {
          if (active) setError(caught.message);
        });
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [processingPublicationKey]);

  useEffect(() => {
    if (!metricsPublicationKey) return;
    let active = true;
    const publicationIds = metricsPublicationKey.split(",");
    const sync = () => {
      void (async () => {
        const updatedProjects: Project[] = [];
        for (const publicationId of publicationIds) {
          updatedProjects.push(await syncMetricSnapshot(publicationId));
        }
        return updatedProjects;
      })()
        .then((updatedProjects) => {
          if (!active) return;
          const latest = new Map(
            updatedProjects.map((project) => [project.id, project]),
          );
          setProjects((items) =>
            items.map((project) => latest.get(project.id) ?? project),
          );
        })
        .catch((caught: Error) => {
          if (active) setError(caught.message);
        });
    };
    sync();
    const timer = window.setInterval(sync, 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [metricsPublicationKey]);

  function setOperation(key: string, state?: OperationState) {
    setOperations((current) => {
      if (state) return { ...current, [key]: state };
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  function replaceProject(updated: Project) {
    setProjects((items) =>
      items.map((item) => (item.id === updated.id ? updated : item)),
    );
  }

  async function withOperation<Result>(
    key: string,
    operation: () => Promise<Result>,
    fallback: string,
  ): Promise<Result | undefined> {
    setOperation(key, "working");
    setError(null);
    try {
      return await operation();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : fallback);
    } finally {
      setOperation(key);
    }
  }

  const upload = (data: FormData) =>
    withOperation(
      "project:create",
      async () => {
        const created = await uploadProject(data);
        setProjects((current) => [created, ...current]);
        return created;
      },
      "Upload failed",
    );

  const importUrl = (request: UrlImportRequest) =>
    withOperation(
      "project:create",
      async () => {
        const created = await importProjectUrl(request);
        setProjects((current) => [created, ...current]);
        return created;
      },
      "URL import failed",
    );

  const rename = (id: string, title: string) =>
    withOperation(
      `project:${id}:rename`,
      async () => {
        const updated = await updateProject(id, title);
        replaceProject(updated);
        return updated;
      },
      "Project update failed",
    );

  const remove = (id: string) =>
    withOperation(
      `project:${id}:delete`,
      async () => {
        await deleteProject(id);
        setProjects((items) => items.filter((item) => item.id !== id));
        return true;
      },
      "Project deletion failed",
    );

  const process = (id: string) =>
    withOperation(
      `project:${id}:process`,
      async () => {
        await processProject(id, languages[id], clipTypes[id] ?? []);
        setProjects((items) =>
          items.map((item) =>
            item.id === id ? { ...item, status: "processing" } : item,
          ),
        );
      },
      "Processing failed",
    );

  const saveStyle = (clipId: string, form: HTMLFormElement) =>
    withOperation(
      `clip:${clipId}:style`,
      async () => {
        const clip = projects
          .flatMap((project) => project.clips)
          .find((item) => item.id === clipId);
        if (!clip) throw new Error("Clip is no longer available");
        const updated = await updateClipStyle(clipId, styleUpdate(form, clip));
        replaceProject(updated);
        return updated;
      },
      "Style update failed",
    );

  const translate = (
    clipId: string,
    targetLanguage: string,
    mode: "translated" | "bilingual",
  ) =>
    withOperation(
      `clip:${clipId}:translate`,
      async () => {
        const updated = await translateClip(clipId, targetLanguage, mode);
        replaceProject(updated);
      },
      "Caption translation failed",
    );

  const analyzeTracking = (clipId: string) =>
    withOperation(
      `clip:${clipId}:tracking`,
      async () => {
        const updated = await analyzeClipTracking(clipId);
        replaceProject(updated);
      },
      "Visual tracking failed",
    );

  const uploadSecondaryMedia = (clipId: string, form: HTMLFormElement) =>
    withOperation(
      `clip:${clipId}:asset`,
      async () => {
        const data = new FormData(form);
        for (const field of ["start_seconds", "end_seconds"])
          if (!String(data.get(field) ?? "").trim()) data.delete(field);
        const updated = await uploadClipSecondaryMedia(clipId, data);
        replaceProject(updated);
        form.reset();
      },
      "Secondary media upload failed",
    );

  const removeSecondaryMedia = (clipId: string, assetId: string) =>
    withOperation(
      `clip:${clipId}:asset:${assetId}`,
      async () => {
        const updated = await deleteClipSecondaryMedia(clipId, assetId);
        replaceProject(updated);
      },
      "Secondary media removal failed",
    );

  async function approve(clipId: string, approved: boolean) {
    const key = `clip:${clipId}:approval`;
    const previousStatus = projects
      .flatMap((project) => project.clips)
      .find((clip) => clip.id === clipId)?.approval_status;
    const nextStatus = approved ? "approved" : "rejected";
    setProjects((items) => updateClipApproval(items, clipId, nextStatus));
    setOperation(key, "working");
    setError(null);
    try {
      await setApproval(clipId, approved);
      setProjects((items) => updateClipApproval(items, clipId, nextStatus));
      return true;
    } catch (caught) {
      if (previousStatus)
        setProjects((items) =>
          updateClipApproval(items, clipId, previousStatus),
        );
      setError(caught instanceof Error ? caught.message : "Approval failed");
      return false;
    } finally {
      setOperation(key);
    }
  }

  function render(clipId: string): Promise<void> {
    const key = `clip:${clipId}:render`;
    setOperation(key, "queued");
    const task = renderQueue.current
      .catch(() => undefined)
      .then(async () => {
        setOperation(key, "working");
        setError(null);
        try {
          await renderClip(clipId);
          if (projectId) setProjects([await getProject(projectId)]);
          else setProjects(await listProjects());
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : "Render failed");
        } finally {
          setOperation(key);
        }
      });
    renderQueue.current = task;
    return task;
  }

  const publish = (clipId: string, data: PublicationCreate) =>
    withOperation(
      `clip:${clipId}:publish`,
      async () => {
        const updated = await createPublication(clipId, data);
        replaceProject(updated);
        return updated;
      },
      "Could not save publication",
    );

  const recordMetrics = (publicationId: string, data: MetricCreate) =>
    withOperation(
      `publication:${publicationId}:metrics`,
      async () => {
        const updated = await addMetricSnapshot(publicationId, data);
        replaceProject(updated);
        return updated;
      },
      "Could not save performance metrics",
    );

  const removePublication = (publicationId: string) =>
    withOperation(
      `publication:${publicationId}:delete`,
      async () => {
        const updated = await deletePublication(publicationId);
        replaceProject(updated);
        return updated;
      },
      "Could not remove publication",
    );

  const refreshPublishedPost = (publicationId: string) =>
    withOperation(
      `publication:${publicationId}:refresh`,
      async () => {
        const updated = await refreshPublication(publicationId);
        replaceProject(updated);
        return updated;
      },
      "Could not refresh publication status",
    );

  const syncPublishedMetrics = (publicationId: string) =>
    withOperation(
      `publication:${publicationId}:sync`,
      async () => {
        const updated = await syncMetricSnapshot(publicationId);
        replaceProject(updated);
        return updated;
      },
      "Could not sync platform metrics",
    );

  return {
    accounts,
    approve,
    busy,
    error,
    clipTypes,
    clipTypeSuggestions,
    languages,
    loading,
    operations,
    operationState: (key: string) => operations[key],
    isPending: (key: string) => Boolean(operations[key]),
    importUrl,
    process,
    projects,
    publish,
    recordMetrics,
    refreshPublishedPost,
    syncPublishedMetrics,
    remove,
    removePublication,
    rename,
    render,
    saveStyle,
    translate,
    analyzeTracking,
    uploadSecondaryMedia,
    removeSecondaryMedia,
    setLanguages,
    setClipTypes,
    upload,
  };
}

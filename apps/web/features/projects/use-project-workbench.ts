"use client";

import { useEffect, useState } from "react";

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
import type { Project, SocialAccount } from "../../lib/contracts";
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
  importProjectUrl,
  listProjects,
  processProject,
  updateProject,
  uploadProject,
  type UrlImportRequest,
} from "./api";

type Clip = Project["clips"][number];

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

export function useProjectWorkbench() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [languages, setLanguages] = useState<Record<string, string>>({});
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
    void listProjects()
      .then(setProjects)
      .catch((caught: Error) => setError(caught.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void listSocialAccounts()
      .then(setAccounts)
      .catch((caught: Error) => setError(caught.message));
  }, []);

  useEffect(() => {
    if (!hasProcessingProjects) return;
    let active = true;
    const refresh = () => {
      void listProjects()
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
  }, [hasProcessingProjects]);

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

  async function withBusy<Result>(
    operation: () => Promise<Result>,
    fallback: string,
  ): Promise<Result | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await operation();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  const upload = (data: FormData) =>
    withBusy(async () => {
      const created = await uploadProject(data);
      setProjects((current) => [created, ...current]);
      return created;
    }, "Upload failed");

  const importUrl = (request: UrlImportRequest) =>
    withBusy(async () => {
      const created = await importProjectUrl(request);
      setProjects((current) => [created, ...current]);
      return created;
    }, "URL import failed");

  const rename = (id: string, title: string) =>
    withBusy(async () => {
      const updated = await updateProject(id, title);
      setProjects((items) =>
        items.map((item) => (item.id === id ? updated : item)),
      );
      return updated;
    }, "Project update failed");

  const remove = (id: string) =>
    withBusy(async () => {
      await deleteProject(id);
      setProjects((items) => items.filter((item) => item.id !== id));
      return true;
    }, "Project deletion failed");

  const process = (id: string) =>
    withBusy(async () => {
      await processProject(id, languages[id]);
      setProjects((items) =>
        items.map((item) =>
          item.id === id ? { ...item, status: "processing" } : item,
        ),
      );
    }, "Processing failed");

  const saveStyle = (clipId: string, form: HTMLFormElement) =>
    withBusy(async () => {
      const clip = projects
        .flatMap((project) => project.clips)
        .find((item) => item.id === clipId);
      if (!clip) throw new Error("Clip is no longer available");
      const updated = await updateClipStyle(clipId, styleUpdate(form, clip));
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
    }, "Style update failed");

  const translate = (
    clipId: string,
    targetLanguage: string,
    mode: "translated" | "bilingual",
  ) =>
    withBusy(async () => {
      const updated = await translateClip(clipId, targetLanguage, mode);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
    }, "Caption translation failed");

  const analyzeTracking = (clipId: string) =>
    withBusy(async () => {
      const updated = await analyzeClipTracking(clipId);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
    }, "Visual tracking failed");

  const uploadSecondaryMedia = (clipId: string, form: HTMLFormElement) =>
    withBusy(async () => {
      const data = new FormData(form);
      for (const field of ["start_seconds", "end_seconds"])
        if (!String(data.get(field) ?? "").trim()) data.delete(field);
      const updated = await uploadClipSecondaryMedia(clipId, data);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      form.reset();
    }, "Secondary media upload failed");

  const removeSecondaryMedia = (clipId: string, assetId: string) =>
    withBusy(async () => {
      const updated = await deleteClipSecondaryMedia(clipId, assetId);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
    }, "Secondary media removal failed");

  async function approve(clipId: string, approved: boolean) {
    try {
      const updated = await setApproval(clipId, approved);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Approval failed");
    }
  }

  const render = (clipId: string) =>
    withBusy(async () => {
      await renderClip(clipId);
      setProjects(await listProjects());
    }, "Render failed");

  const publish = (clipId: string, data: PublicationCreate) =>
    withBusy(async () => {
      const updated = await createPublication(clipId, data);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      return updated;
    }, "Could not save publication");

  const recordMetrics = (publicationId: string, data: MetricCreate) =>
    withBusy(async () => {
      const updated = await addMetricSnapshot(publicationId, data);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      return updated;
    }, "Could not save performance metrics");

  const removePublication = (publicationId: string) =>
    withBusy(async () => {
      const updated = await deletePublication(publicationId);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      return updated;
    }, "Could not remove publication");

  const refreshPublishedPost = (publicationId: string) =>
    withBusy(async () => {
      const updated = await refreshPublication(publicationId);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      return updated;
    }, "Could not refresh publication status");

  const syncPublishedMetrics = (publicationId: string) =>
    withBusy(async () => {
      const updated = await syncMetricSnapshot(publicationId);
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      return updated;
    }, "Could not sync platform metrics");

  return {
    accounts,
    approve,
    busy,
    error,
    languages,
    loading,
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
    upload,
  };
}

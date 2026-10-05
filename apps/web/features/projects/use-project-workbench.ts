"use client";

import { useEffect, useState } from "react";

import {
  renderClip,
  setApproval,
  updateClipStyle,
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

function styleUpdate(form: HTMLFormElement): ClipStyleUpdate {
  const data = new FormData(form);
  return {
    frame_style: data.get("frame_style") as Clip["plan"]["frame_style"],
    caption_config: {
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
      const updated = await updateClipStyle(clipId, styleUpdate(form));
      setProjects((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
    }, "Style update failed");

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
    setLanguages,
    upload,
  };
}

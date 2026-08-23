"use client";

import { useEffect, useState } from "react";

import {
  renderClip,
  setApproval,
  updateClipStyle,
  type ClipStyleUpdate,
} from "../clips/api";
import type { Project } from "../../lib/contracts";
import { listProjects, processProject, uploadProject } from "./api";

type Clip = Project["clips"][number];

function styleUpdate(form: HTMLFormElement): ClipStyleUpdate {
  const data = new FormData(form);
  return {
    frame_style: data.get("frame_style") as Clip["plan"]["frame_style"],
    caption_config: {
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [languages, setLanguages] = useState<Record<string, string>>({});
  const hasProcessingProjects = projects.some(
    (project) => project.status === "processing",
  );

  useEffect(() => {
    void listProjects()
      .then(setProjects)
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

  async function withBusy(operation: () => Promise<void>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      await operation();
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
    }, "Upload failed");

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

  return {
    approve,
    busy,
    error,
    languages,
    process,
    projects,
    render,
    saveStyle,
    setLanguages,
    upload,
  };
}

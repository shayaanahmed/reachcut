"use client";
import { useEffect, useRef, useState, type SetStateAction } from "react";
import {
  generateGrowth,
  loadGrowth,
  prepareGrowth,
  saveGrowth,
  type GrowthBrief,
  type GrowthDiagnosis,
} from "./growth-api";

export function useGrowth(clipId: string, refreshKey = "") {
  const [brief, setBriefState] = useState<GrowthBrief | null>(null);
  const [profiles, setProfiles] = useState<
    Record<string, GrowthBrief["profile"]>
  >({});
  const [diagnoses, setDiagnoses] = useState<GrowthDiagnosis[]>([]);
  const [preparation, setPreparation] = useState<{
    status: string;
    error: string | null;
    reasoning: string | null;
  } | null>(null);
  const [automaticEnabled, setAutomaticEnabled] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const dirty = useRef(false);
  const [retry, setRetry] = useState(0);
  function setBrief(value: SetStateAction<GrowthBrief | null>) {
    dirty.current = true;
    setBriefState(value);
  }
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try {
        const data = await loadGrowth(clipId);
        if (!active) return;
        if (!dirty.current) setBriefState(data.brief);
        setProfiles(data.profiles);
        setDiagnoses(data.diagnoses);
        setAutomaticEnabled(data.automatic_enabled ?? true);
        setPreparation(data.preparation ?? null);
        if (data.preparation?.error) setError(data.preparation.error);
        else if (data.preparation?.status === "ready") setError("");
        const working = ["pending", "working"].includes(
          data.preparation?.status ?? "",
        );
        const waiting =
          data.automatic_enabled !== false &&
          !data.brief.creative &&
          !data.preparation;
        const failed = data.preparation?.status === "failed";
        if (working || waiting || failed)
          timer = setTimeout(() => void refresh(), failed ? 15000 : 2500);
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : String(e));
      }
    }
    void refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [clipId, refreshKey, retry]);
  async function optimize() {
    setError("");
    setPending(true);
    try {
      const data = await prepareGrowth(clipId);
      setPreparation(data.preparation);
      dirty.current = false;
      setRetry((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  }
  async function run(action: "save" | "generate") {
    if (!brief) return;
    setPending(true);
    setError("");
    setMessage("");
    try {
      const input = { ...brief, automatic: false };
      const result = await (action === "save"
        ? saveGrowth(clipId, input)
        : generateGrowth(clipId, input));
      dirty.current = true;
      setBriefState(result);
      if (action === "save" && result.account_id)
        setProfiles((p) => ({ ...p, [result.account_id!]: result.profile }));
      setMessage(
        action === "save"
          ? "Growth brief saved."
          : "Draft generated. Review the copy and save your brief.",
      );
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  }
  return {
    brief,
    setBrief,
    profiles,
    diagnoses,
    pending,
    error,
    message,
    run,
    preparation,
    automaticEnabled,
    optimize,
  };
}

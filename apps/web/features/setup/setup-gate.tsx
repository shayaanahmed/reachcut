"use client";

import { useEffect, useState } from "react";

import type { SetupStatus } from "../../lib/contracts";
import { Dashboard } from "../projects/dashboard";
import type { useProjectWorkbench } from "../projects/use-project-workbench";
import { getSetupStatus } from "./api";
import { SetupAssistant } from "./setup-assistant";

type Workbench = ReturnType<typeof useProjectWorkbench>;

export function SetupGate({ workbench }: { workbench: Workbench }) {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let active = true;
    void getSetupStatus()
      .then((result) => {
        if (active) setStatus(result);
      })
      .catch(() => {
        if (active) setStatus(null);
      })
      .finally(() => {
        if (active) setChecked(true);
      });
    return () => {
      active = false;
    };
  }, []);

  if (!checked) {
    return (
      <main className="narrow-page setup-page setup-loading">
        <span className="eyebrow">REACHCUT</span>
        <h1>Checking your local studio…</h1>
      </main>
    );
  }

  if (status?.ready) return <Dashboard workbench={workbench} />;

  return (
    <SetupAssistant
      initialStatus={status ?? undefined}
      onReady={(readyStatus) => setStatus(readyStatus)}
    />
  );
}

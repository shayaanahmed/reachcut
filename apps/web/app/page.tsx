"use client";

import { useProjectWorkbench } from "../features/projects/use-project-workbench";
import { SetupGate } from "../features/setup/setup-gate";

export default function Home() {
  return <SetupGate workbench={useProjectWorkbench()} />;
}

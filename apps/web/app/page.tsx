"use client";

import { Dashboard } from "../features/projects/dashboard";
import { useProjectWorkbench } from "../features/projects/use-project-workbench";

export default function Home() {
  return <Dashboard workbench={useProjectWorkbench()} />;
}

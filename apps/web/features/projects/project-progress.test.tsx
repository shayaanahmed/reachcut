import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Project } from "../../lib/contracts";
import { ProjectProgress } from "./project-progress";

const project = {
  status: "processing",
  stages: [
    {
      name: "probe",
      status: "succeeded",
      progress: 1,
      attempts: 1,
      error: null,
    },
    {
      name: "transcribe",
      status: "running",
      progress: 0.5,
      attempts: 1,
      error: null,
    },
  ],
} as Project;

describe("project progress", () => {
  it("presents persisted stage progress in pipeline order", () => {
    render(<ProjectProgress project={project} />);

    expect(screen.getByText("30%")).toBeTruthy();
    expect(screen.getByText("Track faces & action")).toBeTruthy();
    expect(screen.getByText("Transcribe locally")).toBeTruthy();
    expect(screen.getByText("50% · attempt 1")).toBeTruthy();
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProjectUpload } from "./project-upload";

describe("project import", () => {
  it("offers yt-dlp URL import with authorization", () => {
    render(
      <ProjectUpload
        busy={false}
        onUpload={vi.fn()}
        onImportUrl={vi.fn()}
        onCreated={vi.fn()}
      />,
    );

    expect(screen.getByText("Drop your source video here")).toBeTruthy();
    expect(
      screen.getByText("One source. A complete clip pipeline."),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Import URL" }));
    fireEvent.change(screen.getByLabelText("Public video URL"), {
      target: { value: "https://www.youtube.com/watch?v=abc" },
    });

    expect(screen.getByLabelText("Public video URL")).toBeTruthy();
    expect(screen.getByText("YouTube video")).toBeTruthy();
    expect(
      screen.getByLabelText("Common supported sources").textContent,
    ).toContain("TikTok");
    expect(screen.getByText("A guided local import")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Continue with this video/ }),
    ).toBeTruthy();
    expect(screen.getByText(/I own, license, or have permission/)).toBeTruthy();
  });
});

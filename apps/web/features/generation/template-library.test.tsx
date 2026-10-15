import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TemplateLibrary } from "./template-library";

const api = vi.hoisted(() => ({
  listReferenceTemplates: vi.fn(),
  classifyReferenceTemplate: vi.fn(),
  importReferenceTemplate: vi.fn(),
  uploadReferenceTemplate: vi.fn(),
}));
vi.mock("./template-library-api", () => ({
  ...api,
  referencePosterUrl: () => undefined,
  referenceVideoUrl: (item: { source_url: string }) => item.source_url,
}));
const pending = {
  id: "a".repeat(32),
  name: "Porch animal",
  source_url: "https://example.com/clip.mp4",
  source_category: "doorbell",
  status: "pending",
  blueprint: null,
  duration_seconds: 0,
  error: null,
  analysis_model: null,
  video_url: null,
};
const ready = {
  ...pending,
  status: "ready",
  blueprint: {
    name: "Doorbell surprise",
    base_template: "documentary_realism",
    format: "Doorbell camera",
    tags: ["comedy", "animals"],
    visual_style: "Nighttime infrared footage",
    camera: "Fixed wide camera",
    pacing: "Continuous action",
    story_structure: "Arrival and surprise",
    caption_style: "No captions",
    suitable_for: "Animal surprises",
  },
};

describe("Reference template library", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("requires classification before selection and enables AI matching afterwards", async () => {
    api.listReferenceTemplates.mockResolvedValue([pending]);
    api.classifyReferenceTemplate.mockResolvedValue(ready);
    const onSelect = vi.fn();
    render(<TemplateLibrary selection="none" onSelect={onSelect} />);
    const select = await screen.findByRole("button", { name: "Use template" });
    expect(select).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "Analyze format" }));
    await waitFor(() => expect(select).toHaveProperty("disabled", false));
    fireEvent.click(select);
    expect(onSelect).toHaveBeenCalledWith(pending.id);
    fireEvent.click(screen.getByRole("button", { name: /Auto · AI chooses/ }));
    expect(onSelect).toHaveBeenCalledWith("none");
    expect(screen.getByText(/Doorbell camera · comedy · animals/)).toBeTruthy();
  });

  it("keeps failed classification retryable and filters by source format", async () => {
    api.listReferenceTemplates.mockResolvedValue([pending]);
    api.classifyReferenceTemplate.mockResolvedValue({
      ...pending,
      status: "failed",
      error: "Vision model is offline",
    });
    render(<TemplateLibrary selection="none" onSelect={vi.fn()} />);
    await screen.findByText("Porch animal");
    fireEvent.change(screen.getByLabelText("Search clips"), {
      target: { value: "doorbell" },
    });
    expect(screen.getByText("Porch animal")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Analyze format" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Vision model is offline",
    );
    expect(screen.getByRole("button", { name: "Retry analysis" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Use template" })).toHaveProperty(
      "disabled",
      true,
    );
  });
});

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GeneralSettings } from "./general-settings";

const api = vi.hoisted(() => ({
  getRuntimeSettings: vi.fn(),
  listOllamaModels: vi.fn(),
  saveRuntimeSettings: vi.fn(),
}));

vi.mock("./api", () => api);
afterEach(cleanup);

describe("general settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.saveRuntimeSettings.mockImplementation(async (value) => value);
    api.getRuntimeSettings.mockResolvedValue({
      ollama_base_url: "http://mini-pc.local:11434",
      editorial_model: "qwen3:8b",
      thumbnail_model: "gemma3:12b",
    });
    api.listOllamaModels.mockResolvedValue([
      "qwen3:8b",
      "gemma3:12b",
      "llama3.2:3b",
    ]);
  });

  it("loads installed Ollama models into a select control", async () => {
    render(<GeneralSettings />);

    const modelSelect = await screen.findByRole("combobox", {
      name: /LLM model/,
    });
    await waitFor(() =>
      expect(screen.getByText("3 installed models available.")).toBeTruthy(),
    );

    expect(api.listOllamaModels).toHaveBeenCalledWith(
      "http://mini-pc.local:11434",
    );
    expect(modelSelect.querySelectorAll("option")).toHaveLength(3);
    expect((modelSelect as HTMLSelectElement).value).toBe("qwen3:8b");
  });
});

it("saves distinct models per task and transcription without changing the main model", async () => {
  api.getRuntimeSettings.mockResolvedValue({
    ollama_base_url: "http://local:11434",
    editorial_model: "main",
    thumbnail_model: "vision",
    task_models: {},
    transcription_model: "large-v3-turbo",
    automatic_growth: true,
  });
  api.listOllamaModels.mockResolvedValue([
    "main",
    "vision",
    "qwen3:14b",
    "qwen3:8b",
    "qwen3-vl:8b",
  ]);
  api.saveRuntimeSettings.mockImplementation(async (value) => value);
  render(<GeneralSettings />);
  await screen.findByText("5 installed models available.");
  fireEvent.click(
    screen.getByRole("button", { name: "Use balanced installed choices" }),
  );
  fireEvent.change(
    screen.getByRole("combobox", { name: /Speech transcription/ }),
    { target: { value: "small" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
  await screen.findByText(
    "Settings saved. New AI tasks will use these choices.",
  );
  const sent = api.saveRuntimeSettings.mock.calls.at(-1)![0];
  expect(sent.editorial_model).toBe("main");
  expect(sent.task_models.growth).toBe("qwen3:14b");
  expect(sent.task_models.metadata).toBe("qwen3:8b");
  expect(sent.task_models.visual_review).toBe("qwen3-vl:8b");
  expect(sent.task_models.image_generation).toBeUndefined();
  expect(sent.transcription_model).toBe("small");
});

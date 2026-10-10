import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GeneralSettings } from "./general-settings";

const api = vi.hoisted(() => ({
  getRuntimeSettings: vi.fn(),
  listOllamaModels: vi.fn(),
  saveRuntimeSettings: vi.fn(),
}));

vi.mock("./api", () => api);

describe("general settings", () => {
  beforeEach(() => {
    api.getRuntimeSettings.mockResolvedValue({
      ollama_base_url: "http://mini-pc.local:11434",
      editorial_model: "qwen3:8b",
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

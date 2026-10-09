import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SetupStatus } from "../../lib/contracts";
import * as api from "./api";
import { SetupAssistant } from "./setup-assistant";

vi.mock("./api", () => ({
  getSetupStatus: vi.fn(),
  downloadEditorialModel: vi.fn(),
}));

const missingModel: SetupStatus = {
  ready: false,
  ffmpeg: true,
  ffprobe: true,
  ollama_available: true,
  ollama_version: "0.12.7",
  ollama_install_url: "https://ollama.com/download",
  editorial_model: "qwen3:8b-q4_K_M",
  editorial_model_installed: false,
  editorial_model_size_bytes: null,
  whisper_model: "large-v3-turbo",
  whisper_download_on_first_use: true,
};

describe("first-run setup assistant", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("downloads the configured editorial model through the API", async () => {
    const onReady = vi.fn();
    vi.mocked(api.downloadEditorialModel).mockResolvedValue({
      ...missingModel,
      ready: true,
      editorial_model_installed: true,
      editorial_model_size_bytes: 5_200_000_000,
    });

    render(<SetupAssistant initialStatus={missingModel} onReady={onReady} />);
    fireEvent.click(screen.getByRole("button", { name: "Download model" }));

    expect(await screen.findByText("✓ Installed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Open dashboard/ }));
    expect(onReady).toHaveBeenCalledOnce();
  });

  it("links to the official installer when Ollama is absent", () => {
    render(
      <SetupAssistant
        initialStatus={{ ...missingModel, ollama_available: false }}
      />,
    );

    const link = screen.getByRole("link", { name: /Download Ollama/ });
    expect(link.getAttribute("href")).toBe("https://ollama.com/download");
    expect(
      screen
        .getByRole("button", { name: "Download model" })
        .hasAttribute("disabled"),
    ).toBe(true);
  });
});

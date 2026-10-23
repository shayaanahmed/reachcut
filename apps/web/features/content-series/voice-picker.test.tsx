import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { defaults, type Providers } from "../informative/api";
import { VoicePicker } from "./voice-picker";

afterEach(cleanup);

it.each([
  ["luxtts", "luxtts", "1.7B"],
  ["chatterbox", "chatterbox-tts", "1.7B"],
  ["chatterbox_turbo", "chatterbox-turbo", "1.7B"],
  ["kokoro", "kokoro", "1.7B"],
  ["qwen", "qwen-tts-0.6B", "0.6B"],
  ["tada", "tada-3b-ml", "3B"],
])(
  "restores a saved %s model when reopening voice settings",
  (engine, model, size) => {
    const providers: Providers = {
      narration: {
        connected: true,
        profiles: [{ id: "voice", name: "Narrator" }],
        engines: [
          {
            engine,
            model_name: model,
            display_name: model,
            downloaded: true,
            languages: ["en"],
            supports_delivery: false,
          },
        ],
      },
      research: { search_configured: false, allowed_hosts: [], limitation: "" },
    };
    render(
      <VoicePicker
        settings={{
          ...defaults,
          narration_mode: "voicebox",
          profile_id: "voice",
          engine,
          model_size: size,
        }}
        providers={providers}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("VoiceBox model")).toHaveValue(model);
  },
);

it("restores the selected Qwen size among two installed variants", () => {
  const providers: Providers = {
    narration: {
      connected: true,
      profiles: [],
      engines: ["1.7B", "0.6B"].map((size) => ({
        engine: "qwen",
        model_name: `qwen-tts-${size}`,
        display_name: size,
        downloaded: true,
        languages: ["en"],
        supports_delivery: false,
      })),
    },
    research: { search_configured: false, allowed_hosts: [], limitation: "" },
  };
  render(
    <VoicePicker
      settings={{
        ...defaults,
        narration_mode: "voicebox",
        engine: "qwen",
        model_size: "0.6B",
      }}
      providers={providers}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("VoiceBox model")).toHaveValue("qwen-tts-0.6B");
});

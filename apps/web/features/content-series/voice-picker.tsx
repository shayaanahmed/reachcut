"use client";

import { useState } from "react";
import type { Providers, ShortSettings } from "../informative/api";
import { matchesVoiceModel } from "../informative/voice-models";

export function VoicePicker({
  settings,
  onChange,
  providers,
  disabled = false,
}: {
  settings: ShortSettings;
  onChange: (s: ShortSettings) => void;
  providers: Providers | null;
  disabled?: boolean;
}) {
  const [model, setModel] = useState("");
  const engine = providers?.narration.engines.find((e) =>
    model ? e.model_name === model : matchesVoiceModel(e, settings),
  );
  return (
    <fieldset disabled={disabled} className="series-voice">
      <legend>Voice and narration</legend>
      <label>
        Narration
        <select
          value={settings.narration_mode ?? "voicebox"}
          onChange={(e) =>
            onChange({
              ...settings,
              narration_mode: e.target.value as "none" | "voicebox",
            })
          }
        >
          <option value="voicebox">VoiceBox narration</option>
          <option value="none">
            Silent storyboard video — add voice later
          </option>
        </select>
      </label>
      {settings.narration_mode !== "none" && (
        <>
          <p>
            {providers?.narration.connected
              ? "VoiceBox connected"
              : "VoiceBox is offline or checking. You can create the video now and add a voice later."}
          </p>
          <label>
            VoiceBox voice
            <select
              value={settings.profile_id}
              onChange={(e) =>
                onChange({ ...settings, profile_id: e.target.value })
              }
            >
              <option value="">Choose a voice</option>
              {providers?.narration.profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            VoiceBox model
            <select
              value={engine?.model_name ?? ""}
              onChange={(e) => {
                setModel(e.target.value);
                const selected = providers?.narration.engines.find(
                  (item) => item.model_name === e.target.value,
                );
                if (selected)
                  onChange({
                    ...settings,
                    engine: selected.engine,
                    model_size: selected.model_name.includes("0.6B")
                      ? "0.6B"
                      : selected.model_name.toLowerCase().includes("3b")
                        ? "3B"
                        : selected.engine === "tada"
                          ? "1B"
                          : "1.7B",
                    delivery: selected.supports_delivery
                      ? settings.delivery
                      : "",
                  });
              }}
            >
              <option value="">Choose an installed model</option>
              {providers?.narration.engines.map((e) => (
                <option
                  key={e.model_name}
                  value={e.model_name}
                  disabled={!e.downloaded}
                >
                  {e.display_name}
                  {!e.downloaded ? " · install in VoiceBox" : ""}
                </option>
              ))}
            </select>
          </label>
        </>
      )}
    </fieldset>
  );
}

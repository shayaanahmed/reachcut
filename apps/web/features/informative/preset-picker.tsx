"use client";
import { useEffect, useState } from "react";
import { request } from "./api";
import type { Preset } from "./api";

export function ChannelPresetPicker({ disabled }: { disabled: boolean }) {
  const [presets, setPresets] = useState<Preset[]>([]);
  useEffect(() => {
    let active = true;
    void request<Preset[]>("/channel-presets")
      .then((items) => {
        if (active) setPresets(items);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  return (
    <label>
      Channel preset
      <select name="preset_id" disabled={disabled}>
        <option value="">No preset</option>
        {presets.map((preset) => (
          <option key={preset.id} value={preset.id}>
            {preset.name}
          </option>
        ))}
      </select>
      <small>
        Inherits language and caption identity; video changes keep the saved
        preset.
      </small>
    </label>
  );
}

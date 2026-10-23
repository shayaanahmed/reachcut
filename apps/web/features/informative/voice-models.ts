import type { Providers, ShortSettings } from "./api";

export function matchesVoiceModel(
  model: Providers["narration"]["engines"][number],
  settings: Pick<ShortSettings, "engine" | "model_size">,
) {
  return (
    model.engine === settings.engine &&
    (["kokoro", "luxtts", "chatterbox", "chatterbox_turbo"].includes(
      model.engine,
    ) ||
      model.model_name
        .toLowerCase()
        .includes(settings.model_size.toLowerCase()))
  );
}

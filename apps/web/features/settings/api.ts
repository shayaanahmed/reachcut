import {
  runtimeSettingsSchema,
  type RuntimeSettings,
} from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

export async function getRuntimeSettings(): Promise<RuntimeSettings> {
  const response = await fetch(`${API_URL}/settings`, { cache: "no-store" });
  if (!response.ok)
    throw await responseError(response, "Could not load settings");
  return runtimeSettingsSchema.parse(await response.json());
}

export async function saveRuntimeSettings(
  settings: RuntimeSettings,
): Promise<RuntimeSettings> {
  const response = await fetch(`${API_URL}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!response.ok)
    throw await responseError(response, "Could not save settings");
  return runtimeSettingsSchema.parse(await response.json());
}

export async function listOllamaModels(baseUrl: string): Promise<string[]> {
  const query = new URLSearchParams({ base_url: baseUrl });
  const response = await fetch(`${API_URL}/settings/ollama/models?${query}`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw await responseError(response, "Could not connect to Ollama");
  const payload = (await response.json()) as { models: string[] };
  return payload.models;
}

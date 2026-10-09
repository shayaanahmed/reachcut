import { setupStatusSchema, type SetupStatus } from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

export async function getSetupStatus(): Promise<SetupStatus> {
  const response = await fetch(`${API_URL}/setup/status`, {
    cache: "no-store",
  });
  if (!response.ok) throw await responseError(response, "Setup check failed");
  return setupStatusSchema.parse(await response.json());
}

export async function downloadEditorialModel(): Promise<SetupStatus> {
  const response = await fetch(`${API_URL}/setup/editorial-model`, {
    method: "POST",
  });
  if (!response.ok)
    throw await responseError(response, "Model download failed");
  return setupStatusSchema.parse(await response.json());
}

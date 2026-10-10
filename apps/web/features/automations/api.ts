import {
  automationPipelineSchema,
  type AutomationPipeline,
  type ClipType,
} from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

export type AutomationCreate = {
  name: string;
  project_id: string;
  social_account_ids: string[];
  clip_selection: "all" | "best";
  clip_types: ClipType[];
  schedule: "once" | "daily" | "weekly";
  next_run_at: string;
  title_template: string;
  description_template: string;
};

export async function listAutomations(): Promise<AutomationPipeline[]> {
  const response = await fetch(`${API_URL}/automations`, { cache: "no-store" });
  if (!response.ok)
    throw await responseError(response, "Could not load automations");
  return automationPipelineSchema.array().parse(await response.json());
}

export async function createAutomation(
  data: AutomationCreate,
): Promise<AutomationPipeline> {
  const response = await fetch(`${API_URL}/automations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok)
    throw await responseError(response, "Could not create automation");
  return automationPipelineSchema.parse(await response.json());
}

export async function runAutomation(id: string): Promise<void> {
  const response = await fetch(`${API_URL}/automations/${id}/run`, {
    method: "POST",
  });
  if (!response.ok)
    throw await responseError(response, "Could not run automation");
}

export async function setAutomationActive(
  id: string,
  active: boolean,
): Promise<AutomationPipeline> {
  const response = await fetch(`${API_URL}/automations/${id}/active`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  });
  if (!response.ok)
    throw await responseError(response, "Could not update pipeline");
  return automationPipelineSchema.parse(await response.json());
}

export async function deleteAutomation(id: string): Promise<void> {
  const response = await fetch(`${API_URL}/automations/${id}`, {
    method: "DELETE",
  });
  if (!response.ok)
    throw await responseError(response, "Could not delete automation");
}

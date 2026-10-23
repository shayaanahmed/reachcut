import { z } from "zod";
import { API_URL, responseError } from "../../lib/http";

const runSchema = z.object({
  id: z.string(),
  source_project_id: z.string().nullable(),
  source_title: z.string(),
  target_project_id: z.string(),
  kind: z.enum(["clips", "full", "metadata", "language"]),
  target_language: z.string().nullable(),
  scopes: z.array(z.string()),
  clip_ids: z.array(z.string()),
  status: z.string(),
  error: z.string().nullable(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
});
const stateSchema = z.object({
  speech_available: z.boolean().nullable(),
  runs: z.array(runSchema),
});
export type WorkflowState = z.infer<typeof stateSchema>;
export type WorkflowKind = z.infer<typeof runSchema>["kind"];
export async function loadWorkflows(id: string) {
  const response = await fetch(`${API_URL}/projects/${id}/workflows`, {
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok)
    throw await responseError(response, "Could not load source workflows");
  return stateSchema.parse(await response.json());
}
export async function startWorkflow(
  id: string,
  payload: {
    idempotency_key: string;
    kind: WorkflowKind;
    clip_ids: string[];
    target_language?: string;
    scopes: string[];
  },
  narration?: File,
) {
  const body = new FormData();
  body.set("payload", JSON.stringify(payload));
  if (narration) body.set("narration", narration);
  const response = await fetch(`${API_URL}/projects/${id}/workflows`, {
    method: "POST",
    body,
    signal: AbortSignal.timeout(120000),
  });
  if (!response.ok)
    throw await responseError(response, "Could not start source workflow");
  return runSchema.parse(await response.json());
}
export async function retryWorkflow(id: string) {
  const response = await fetch(`${API_URL}/workflow-runs/${id}/retry`, {
    method: "POST",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok)
    throw await responseError(response, "Could not retry workflow");
  return runSchema.parse(await response.json());
}

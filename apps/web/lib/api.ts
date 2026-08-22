import { projectSchema, type Project } from "./contracts";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export async function listProjects(): Promise<Project[]> {
  const response = await fetch(`${API_URL}/projects`, { cache: "no-store" });
  if (!response.ok)
    throw new Error(`Could not load projects (${response.status})`);
  return projectSchema.array().parse(await response.json());
}

export async function uploadProject(data: FormData): Promise<Project> {
  const response = await fetch(`${API_URL}/projects/upload`, {
    method: "POST",
    body: data,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `Upload failed (${response.status})`);
  }
  return projectSchema.parse(await response.json());
}

export async function processProject(projectId: string): Promise<void> {
  const response = await fetch(`${API_URL}/projects/${projectId}/process`, {
    method: "POST",
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      payload?.detail ?? `Processing failed (${response.status})`,
    );
  }
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await fetch(`${API_URL}/projects/${projectId}`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw new Error(`Could not load project (${response.status})`);
  return projectSchema.parse(await response.json());
}

export async function setApproval(
  clipId: string,
  approved: boolean,
): Promise<Project> {
  const response = await fetch(`${API_URL}/clips/${clipId}/approval`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
  if (!response.ok)
    throw new Error(`Could not update approval (${response.status})`);
  return projectSchema.parse(await response.json());
}

export const previewUrl = (clipId: string) =>
  `${API_URL}/clips/${clipId}/preview`;

export async function renderClip(clipId: string): Promise<void> {
  const response = await fetch(`${API_URL}/clips/${clipId}/render`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(`Final render failed (${response.status})`);
}

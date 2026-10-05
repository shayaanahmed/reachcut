import { projectSchema, type Project } from "../../lib/contracts";
import { API_URL, responseError, UPLOAD_API_URL } from "../../lib/http";

export async function listProjects(): Promise<Project[]> {
  const response = await fetch(`${API_URL}/projects`, { cache: "no-store" });
  if (!response.ok)
    throw new Error(`Could not load projects (${response.status})`);
  return projectSchema.array().parse(await response.json());
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await fetch(`${API_URL}/projects/${projectId}`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw new Error(`Could not load project (${response.status})`);
  return projectSchema.parse(await response.json());
}

export async function uploadProject(data: FormData): Promise<Project> {
  const response = await fetch(`${UPLOAD_API_URL}/projects/upload`, {
    method: "POST",
    body: data,
  });
  if (!response.ok) throw await responseError(response, "Upload failed");
  return projectSchema.parse(await response.json());
}

export type UrlImportRequest = {
  title: string;
  url: string;
  authorization_confirmed: boolean;
};

export async function importProjectUrl(
  request: UrlImportRequest,
): Promise<Project> {
  const response = await fetch(`${UPLOAD_API_URL}/projects/import-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw await responseError(response, "URL import failed");
  return projectSchema.parse(await response.json());
}

export async function updateProject(
  projectId: string,
  title: string,
): Promise<Project> {
  const response = await fetch(`${API_URL}/projects/${projectId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok)
    throw await responseError(response, "Project update failed");
  return projectSchema.parse(await response.json());
}

export async function deleteProject(projectId: string): Promise<void> {
  const response = await fetch(`${API_URL}/projects/${projectId}`, {
    method: "DELETE",
  });
  if (!response.ok)
    throw await responseError(response, "Project deletion failed");
}

export async function processProject(
  projectId: string,
  language?: string,
): Promise<void> {
  const response = await fetch(`${API_URL}/projects/${projectId}/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language: language || null }),
  });
  if (!response.ok) throw await responseError(response, "Processing failed");
}

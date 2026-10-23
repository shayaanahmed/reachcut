import {
  clipTypeSuggestionSchema,
  projectSchema,
  type ClipType,
  type ClipTypeSuggestion,
  type Project,
} from "../../lib/contracts";
import {
  API_URL,
  errorMessage,
  responseError,
  UPLOAD_API_URL,
} from "../../lib/http";

export async function listProjects(): Promise<Project[]> {
  const response = await fetch(`${API_URL}/projects`, { cache: "no-store" });
  if (!response.ok)
    throw new Error(`Could not load source videos (${response.status})`);
  return projectSchema.array().parse(await response.json());
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await fetch(`${API_URL}/projects/${projectId}`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw new Error(`Could not load source video (${response.status})`);
  return projectSchema.parse(await response.json());
}

export async function uploadProject(
  data: FormData,
  onProgress?: (percent: number) => void,
): Promise<Project> {
  if (onProgress) {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", `${UPLOAD_API_URL}/projects/upload`);
      request.upload.onprogress = (event) => {
        if (event.lengthComputable)
          onProgress(Math.round((event.loaded / event.total) * 100));
      };
      request.onerror = () =>
        reject(new Error("Upload failed. Check your connection and retry."));
      request.onload = () => {
        try {
          let payload: unknown;
          try {
            payload = JSON.parse(request.responseText);
          } catch {
            payload = null;
          }
          if (request.status < 200 || request.status >= 300) {
            throw new Error(
              errorMessage(payload, `Upload failed (${request.status})`),
            );
          }
          resolve(projectSchema.parse(payload));
        } catch (error) {
          reject(error);
        }
      };
      request.send(data);
    });
  }
  const response = await fetch(`${UPLOAD_API_URL}/projects/upload`, {
    method: "POST",
    body: data,
  });
  if (!response.ok) throw await responseError(response, "Upload failed");
  return projectSchema.parse(await response.json());
}

export async function uploadPublishingVideo(data: FormData): Promise<Project> {
  const response = await fetch(
    `${UPLOAD_API_URL}/projects/upload-for-publishing`,
    {
      method: "POST",
      body: data,
    },
  );
  if (!response.ok) throw await responseError(response, "Video upload failed");
  return projectSchema.parse(await response.json());
}

export type UrlImportRequest = {
  preset_id?: string;
  language?: string | null;
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
    throw await responseError(response, "Source video update failed");
  return projectSchema.parse(await response.json());
}

export async function deleteProject(projectId: string): Promise<void> {
  const response = await fetch(`${API_URL}/projects/${projectId}`, {
    method: "DELETE",
  });
  if (!response.ok)
    throw await responseError(response, "Source video deletion failed");
}

export async function processProject(
  projectId: string,
  language?: string,
  clipTypes: ClipType[] = [],
  processingMode: "clips" | "metadata" = "clips",
): Promise<void> {
  const response = await fetch(`${API_URL}/projects/${projectId}/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      language: language || null,
      clip_types: clipTypes,
      processing_mode: processingMode,
    }),
  });
  if (!response.ok) throw await responseError(response, "Processing failed");
}

export async function getClipTypeSuggestions(
  projectId: string,
): Promise<ClipTypeSuggestion[]> {
  const response = await fetch(`${API_URL}/projects/${projectId}/clip-types`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw await responseError(response, "Could not load clip directions");
  return clipTypeSuggestionSchema.array().parse(await response.json());
}

export async function stopProject(projectId: string): Promise<void> {
  const response = await fetch(`${API_URL}/projects/${projectId}/cancel`, {
    method: "POST",
  });
  if (!response.ok)
    throw await responseError(response, "Could not stop source video");
}

export async function retryProject(projectId: string): Promise<void> {
  const response = await fetch(`${API_URL}/projects/${projectId}/retry`, {
    method: "POST",
  });
  if (!response.ok)
    throw await responseError(response, "Could not retry source video");
}

export type QualityReview = {
  limitations: string;
  clips: {
    clip_id: string;
    findings: {
      message: string;
      start: number;
      severity: string;
      basis: string;
    }[];
    corrections: { attempt: number; action: string }[];
  }[];
};
export async function getQualityReview(id: string): Promise<QualityReview> {
  const response = await fetch(`${API_URL}/projects/${id}/quality`);
  if (!response.ok)
    throw await responseError(response, "Could not load quality review");
  return response.json() as Promise<QualityReview>;
}

import { z } from "zod";
import { type Project, projectSchema } from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

import {
  createPublicationBatch,
  publishProjectBatch,
  type PublicationCreate,
  type BulkPublishResult,
} from "./api";

const editSchema = z.object({ title: z.string(), description: z.string() });
const managementSchema = z.object({
  capabilities: z.object({
    update: z.boolean(),
    delete: z.boolean(),
    title: z.boolean(),
    explanation: z.string(),
    reconnect_required: z.boolean().default(false),
    connection_issue: z.string().nullable().optional(),
    reconnect_url: z.string().nullable().optional(),
    deletion_issue: z.string().nullable().optional(),
    deletion_reconnect_required: z.boolean().default(false),
  }),
  suggested: editSchema,
  needs_update: z.boolean(),
  hashtag_notice: z.string().nullable().optional(),
  draft_revision: z.string().optional(),
  operation: z
    .object({
      state: z.string(),
      action: z.string(),
      error: z.string().nullable(),
    })
    .nullable(),
  history: z.array(
    z.object({
      action: z.string(),
      before: z.record(z.string(), z.unknown()),
      after: z.record(z.string(), z.unknown()),
      created_at: z.string(),
    }),
  ),
});
export type PostManagementData = z.infer<typeof managementSchema>;
export type PostEdit = z.infer<typeof editSchema>;
async function request(path: string, method = "GET", body?: unknown) {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    cache: "no-store",
    signal: AbortSignal.timeout(method === "GET" ? 15000 : 150000),
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok)
    throw await responseError(response, "Could not manage the social post");
  return response.json();
}
export async function getPostManagement(id: string) {
  return managementSchema.parse(
    await request(`/publications/${id}/management`),
  );
}
export async function updateRemotePost(id: string, edit: PostEdit) {
  return projectSchema.parse(
    await request(`/publications/${id}/remote`, "PUT", edit),
  );
}
export async function deleteRemotePost(id: string) {
  return projectSchema.parse(
    await request(`/publications/${id}/delete-remote`, "POST", {
      confirm: true,
    }),
  );
}
export async function publishSeparatePost(id: string) {
  return projectSchema.parse(
    await request(`/publications/${id}/publish-new`, "POST", { confirm: true }),
  );
}

export type PublishingOutcome = {
  accountId: string;
  platform: string;
  state: "updated" | "queued" | "current" | "manual" | "blocked" | "failed";
  message: string;
};
export type PublishingReport = { outcomes: PublishingOutcome[] };

// A result for every destination makes partial success explicit and safe to retry.
export async function savePublishingDestinations(
  clip: Project["clips"][number],
  requests: PublicationCreate[],
  onChanged: (project: Project) => void,
): Promise<PublishingReport> {
  const outcomes: PublishingOutcome[] = [];
  for (const request of requests) {
    const posts = clip.publications.filter(
      (post) => post.social_account_id === request.social_account_id,
    );
    const original = posts
      .filter((post) => post.status === "published")
      .toSorted(
        (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
      )[0];
    const outcome = {
      accountId: request.social_account_id,
      platform: original?.platform ?? posts[0]?.platform ?? "destination",
    };
    if (
      posts.some((post) =>
        ["queued", "processing", "uncertain", "deferred"].includes(post.status),
      )
    ) {
      outcomes.push({
        ...outcome,
        state: "blocked",
        message:
          "An upload is already queued, processing, paused, or awaiting verification. Check its status before retrying.",
      });
      continue;
    }
    try {
      if (!original) {
        const updated = await createPublicationBatch(clip.id, [request]);
        onChanged(updated);
        outcomes.push({
          ...outcome,
          state: "queued",
          message: "New upload queued. Follow its status below.",
        });
        continue;
      }
      const details = await getPostManagement(original.id);
      if (!details.capabilities.update) {
        outcomes.push({
          ...outcome,
          state: "manual",
          message: details.capabilities.explanation,
        });
      } else if (details.capabilities.reconnect_required) {
        outcomes.push({
          ...outcome,
          state: "blocked",
          message:
            details.capabilities.connection_issue ??
            "Reconnect this account in Accounts.",
        });
      } else if (details.operation?.state === "working") {
        outcomes.push({
          ...outcome,
          state: "blocked",
          message:
            "An update is already in progress. Check the original post before retrying.",
        });
      } else if (
        request.description === original.description &&
        (!details.capabilities.title || request.title === original.title)
      ) {
        outcomes.push({
          ...outcome,
          state: "current",
          message: "Already uses this publishing copy. No update was sent.",
        });
      } else {
        const updated = await updateRemotePost(original.id, {
          title: request.title,
          description: request.description,
        });
        onChanged(updated);
        outcomes.push({
          ...outcome,
          state: "updated",
          message: "Existing post updated. Its ID and metrics were preserved.",
        });
      }
    } catch (error) {
      outcomes.push({
        ...outcome,
        state: "failed",
        message:
          error instanceof Error
            ? error.message
            : "Publishing failed. Check this destination before retrying.",
      });
    }
  }
  return { outcomes };
}

export async function publishAndUpdateProject(
  projectId: string,
  clipIds: string[],
  accountIds: string[],
  onChanged: (project: Project) => void,
): Promise<BulkPublishResult> {
  const result = await publishProjectBatch(projectId, clipIds, accountIds);
  onChanged(result.project);
  const skipped: BulkPublishResult["skipped"] = [];
  let updated = 0;
  for (const entry of result.skipped) {
    const clip = result.project.clips.find((item) => item.id === entry.clip_id);
    const posts =
      clip?.publications.filter(
        (post) => post.social_account_id === entry.account_id,
      ) ?? [];
    const original = posts
      .filter((post) => post.status === "published")
      .toSorted(
        (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
      )[0];
    if (
      !original ||
      clip?.approval_status !== "approved" ||
      !clip.final_path ||
      posts.some((post) =>
        ["queued", "processing", "uncertain", "deferred"].includes(post.status),
      )
    ) {
      skipped.push(entry);
      continue;
    }
    try {
      const details = await getPostManagement(original.id);
      if (details.capabilities.reconnect_required) {
        skipped.push({
          ...entry,
          reason:
            details.capabilities.connection_issue ??
            "Reconnect this account in Accounts",
        });
      } else if (!details.capabilities.update) {
        skipped.push({
          ...entry,
          reason: `Open the existing ${original.platform} post to edit its copy. This integration cannot update it.`,
        });
      } else if (!details.needs_update) {
        skipped.push({
          ...entry,
          reason: "Existing post already uses the latest publishing copy",
        });
      } else {
        result.project = await updateRemotePost(original.id, details.suggested);
        onChanged(result.project);
        updated++;
      }
    } catch (error) {
      skipped.push({
        ...entry,
        reason:
          error instanceof Error
            ? error.message
            : "Existing post update failed",
      });
    }
  }
  return { ...result, updated, skipped };
}

import {
  accountConnectionReadinessSchema,
  projectSchema,
  socialAccountSchema,
  type AccountConnectionReadiness,
  type Project,
  type SocialAccount,
  type SocialPlatform,
} from "../../lib/contracts";
import { API_URL, responseError } from "../../lib/http";

type Clip = Project["clips"][number];

export type Platform = Clip["publications"][number]["platform"];

export type PublicationCreate = {
  social_account_id: string;
  title: string;
  description: string;
  privacy_status: "public" | "unlisted" | "friends" | "private";
};

export type PublishingCapabilities = {
  youtube_configured: boolean;
  automatic_platforms: SocialPlatform[];
  configured_platforms: SocialPlatform[];
};

export type SocialAccountCreate = {
  platform: SocialPlatform;
  label: string;
  username: string;
  profile_url: string | null;
  default_hashtags: string[];
  default_cta: string;
  default_campaign_url: string | null;
  currency: string;
  is_default: boolean;
};

export type SocialAccountUpdate = Omit<SocialAccountCreate, "platform">;

export type MetricCreate = {
  views: number;
  likes: number;
  comments: number;
  shares: number;
  watch_time_seconds: number | null;
  followers_gained: number;
  affiliate_clicks: number;
  conversions: number;
  revenue: number;
  currency: string;
};

export async function createPublication(
  clipId: string,
  data: PublicationCreate,
): Promise<Project> {
  const response = await fetch(`${API_URL}/clips/${clipId}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok)
    throw await responseError(response, "Could not publish clip");
  return projectSchema.parse(await response.json());
}

export async function addMetricSnapshot(
  publicationId: string,
  data: MetricCreate,
): Promise<Project> {
  const response = await fetch(
    `${API_URL}/publications/${publicationId}/metrics`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    },
  );
  if (!response.ok)
    throw await responseError(response, "Could not save performance metrics");
  return projectSchema.parse(await response.json());
}

export async function syncMetricSnapshot(
  publicationId: string,
): Promise<Project> {
  const response = await fetch(
    `${API_URL}/publications/${publicationId}/metrics/sync`,
    { method: "POST" },
  );
  if (!response.ok)
    throw await responseError(response, "Could not sync platform metrics");
  return projectSchema.parse(await response.json());
}

export async function deletePublication(
  publicationId: string,
): Promise<Project> {
  const response = await fetch(`${API_URL}/publications/${publicationId}`, {
    method: "DELETE",
  });
  if (!response.ok)
    throw await responseError(response, "Could not remove publication");
  return projectSchema.parse(await response.json());
}

export async function refreshPublication(
  publicationId: string,
): Promise<Project> {
  const response = await fetch(
    `${API_URL}/publications/${publicationId}/refresh`,
    { method: "POST" },
  );
  if (!response.ok)
    throw await responseError(response, "Could not refresh publication status");
  return projectSchema.parse(await response.json());
}

export async function listSocialAccounts(): Promise<SocialAccount[]> {
  const response = await fetch(`${API_URL}/social-accounts`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw await responseError(response, "Could not load social accounts");
  return socialAccountSchema.array().parse(await response.json());
}

export async function socialAccountReadiness(): Promise<
  AccountConnectionReadiness[]
> {
  const response = await fetch(`${API_URL}/social-accounts/readiness`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw await responseError(response, "Could not verify account readiness");
  return accountConnectionReadinessSchema.array().parse(await response.json());
}

export async function createSocialAccount(
  data: SocialAccountCreate,
): Promise<SocialAccount> {
  const response = await fetch(`${API_URL}/social-accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok)
    throw await responseError(response, "Could not create social account");
  return socialAccountSchema.parse(await response.json());
}

export async function updateSocialAccount(
  accountId: string,
  data: SocialAccountUpdate,
): Promise<SocialAccount> {
  const response = await fetch(`${API_URL}/social-accounts/${accountId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok)
    throw await responseError(response, "Could not update social account");
  return socialAccountSchema.parse(await response.json());
}

export async function archiveSocialAccount(accountId: string): Promise<void> {
  const response = await fetch(`${API_URL}/social-accounts/${accountId}`, {
    method: "DELETE",
  });
  if (!response.ok)
    throw await responseError(response, "Could not archive social account");
}

export async function publishingCapabilities(): Promise<PublishingCapabilities> {
  const response = await fetch(`${API_URL}/publishing/capabilities`, {
    cache: "no-store",
  });
  if (!response.ok)
    throw await responseError(response, "Could not load publishing setup");
  return (await response.json()) as PublishingCapabilities;
}

export function socialConnectUrl(accountId: string): string {
  return `${API_URL}/social-accounts/${accountId}/connect`;
}

export async function disconnectSocialAccount(
  accountId: string,
): Promise<SocialAccount> {
  const response = await fetch(
    `${API_URL}/social-accounts/${accountId}/connection`,
    { method: "DELETE" },
  );
  if (!response.ok)
    throw await responseError(response, "Could not disconnect account");
  return socialAccountSchema.parse(await response.json());
}

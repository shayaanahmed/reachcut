export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";
export const UPLOAD_API_URL = process.env.NEXT_PUBLIC_UPLOAD_API_URL ?? API_URL;

export async function responseError(
  response: Response,
  fallback: string,
): Promise<Error> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: string;
  } | null;
  return new Error(payload?.detail ?? `${fallback} (${response.status})`);
}

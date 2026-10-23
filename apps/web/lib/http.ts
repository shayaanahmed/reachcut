export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";
export const UPLOAD_API_URL =
  process.env.NEXT_PUBLIC_UPLOAD_API_URL ?? "http://127.0.0.1:8000/api";

export async function responseError(
  response: Response,
  fallback: string,
): Promise<Error> {
  return new Error(
    errorMessage(
      await response.json().catch(() => null),
      `${fallback} (${response.status})`,
    ),
  );
}

export function errorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object" || !("detail" in payload))
    return fallback;
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (!Array.isArray(detail)) return fallback;
  const messages = detail.flatMap((issue: unknown) => {
    if (
      !issue ||
      typeof issue !== "object" ||
      !("msg" in issue) ||
      typeof issue.msg !== "string"
    )
      return [];
    const location =
      "loc" in issue && Array.isArray(issue.loc)
        ? issue.loc
            .filter(
              (part: unknown) =>
                (typeof part === "string" && part !== "body") ||
                typeof part === "number",
            )
            .join(".")
        : "";
    return [location ? `${location}: ${issue.msg}` : issue.msg];
  });
  return messages.join("; ") || fallback;
}

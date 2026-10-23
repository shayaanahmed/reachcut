export function captionWithTags(caption: string, hashtags: string[]): string {
  const existing = new Set(
    (caption.match(/#[^\s#]+/gu) ?? []).map((tag) =>
      tag.replace(/[.,!?:;]+$/u, "").toLowerCase(),
    ),
  );
  const additions = hashtags.filter((tag) => {
    const key = tag.toLowerCase();
    if (existing.has(key)) return false;
    existing.add(key);
    return true;
  });
  return [caption.trim(), additions.join(" ")].filter(Boolean).join("\n\n");
}

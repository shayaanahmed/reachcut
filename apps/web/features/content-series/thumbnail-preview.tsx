import type { ThumbnailDesign } from "./api";

export function ThumbnailPreview({
  design,
  name,
  subject = "Your next subject",
  headline,
}: {
  design: ThumbnailDesign;
  name: string;
  subject?: string;
  headline?: string;
}) {
  const title = design.headline_template
    .replaceAll("{subject}", subject)
    .replaceAll("{series}", name)
    .replaceAll("{headline}", headline ?? subject);
  return (
    <div
      className={`series-thumbnail layout-${design.layout}`}
      role="img"
      aria-label={`Thumbnail preview: ${title}`}
      style={{
        background: design.background,
        color: design.foreground,
        borderColor: design.accent,
      }}
    >
      <span className="thumbnail-label" style={{ color: design.accent }}>
        {design.label || name}
      </span>
      <strong>{title}</strong>
      <span className="thumbnail-subject" style={{ color: design.accent }}>
        {subject}
      </span>
    </div>
  );
}

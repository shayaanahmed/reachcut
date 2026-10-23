import Link from "next/link";
import type { ReactNode } from "react";

export function ActionLink({
  href,
  children,
  icon = "↗",
  primary = false,
  description,
}: {
  href: string;
  children: ReactNode;
  icon?: string;
  primary?: boolean;
  description?: string;
}) {
  return (
    <Link
      href={href}
      className={`action-link ${primary ? "action-link-primary" : ""}`}
    >
      <span className="action-link-icon" aria-hidden="true">
        {icon}
      </span>
      <span>
        <strong>{children}</strong>
        {description && <small>{description}</small>}
      </span>
      <span className="action-link-arrow" aria-hidden="true">
        →
      </span>
    </Link>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./styles.css";

const personalBuild = process.env.NEXT_PUBLIC_REACHCUT_CHANNEL === "personal";
const applicationName = personalBuild ? "ReachCut Personal" : "ReachCut";

export const metadata: Metadata = {
  title: `${applicationName} — Video repurposing workspace`,
  description: "A private, local-first workspace for creating vertical clips",
  applicationName,
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            <Link
              className="brand"
              href="/"
              aria-label={`${applicationName} dashboard`}
            >
              <span className="brand-mark">R</span>
              <span>
                <strong>{applicationName}</strong>
                <small>
                  {personalBuild ? "Personal channel" : "Local studio"}
                </small>
              </span>
            </Link>
            <nav aria-label="Primary navigation">
              <Link href="/">
                <span aria-hidden="true">⌂</span> Dashboard
              </Link>
              <Link href="/projects">
                <span aria-hidden="true">▤</span> Projects
              </Link>
              <Link href="/discover">
                <span aria-hidden="true">⌁</span> Discover
              </Link>
              <Link href="/settings/accounts">
                <span aria-hidden="true">⚙</span> Accounts
              </Link>
              <Link href="/setup">
                <span aria-hidden="true">✓</span> Setup
              </Link>
            </nav>
            <div className="sidebar-footer">
              <span className="online-dot" /> Local processing
              <small>Your media stays in your configured data directory.</small>
            </div>
          </aside>
          <div className="app-content">{children}</div>
        </div>
      </body>
    </html>
  );
}

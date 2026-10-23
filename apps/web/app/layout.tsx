import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./styles.css";

export const metadata: Metadata = {
  title: "ReachCut — Video repurposing workspace",
  description: "A private, local-first workspace for creating vertical clips",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            <Link className="brand" href="/" aria-label="ReachCut dashboard">
              <span className="brand-mark">R</span>
              <span>
                <strong>ReachCut</strong>
                <small>Local studio</small>
              </span>
            </Link>
            <nav aria-label="Primary navigation">
              <Link href="/">
                <span aria-hidden="true">⌂</span> Dashboard
              </Link>
              <Link href="/projects">
                <span aria-hidden="true">▤</span> Source videos
              </Link>
              <Link href="/publishing">
                <span aria-hidden="true">↗</span> Publishing
              </Link>
              <Link href="/publishing/posts">
                <span aria-hidden="true">☷</span> Social posts
              </Link>
              <Link href="/studio">
                <span aria-hidden="true">✂</span> Studio
              </Link>
              <Link href="/insights">
                <span aria-hidden="true">▥</span> Insights
              </Link>
              <Link href="/growth">
                <span aria-hidden="true">✦</span> Growth
              </Link>
              <Link href="/created">
                <span aria-hidden="true">◫</span> Created videos
              </Link>
              <Link href="/create">
                <span aria-hidden="true">✦</span> Create a short
              </Link>
              <Link href="/projects/new">
                <span aria-hidden="true">＋</span> Clip a video
              </Link>
              <Link href="/frames">
                <span aria-hidden="true">◈</span> Frame library
              </Link>
              <Link href="/automations">
                <span aria-hidden="true">↻</span> Automations
              </Link>
              <Link href="/settings/accounts">
                <span aria-hidden="true">⚙</span> Accounts
              </Link>
              <Link href="/settings/general">
                <span aria-hidden="true">⋯</span> Settings
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

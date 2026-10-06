"use client";

import { type FormEvent, useState } from "react";

import type { Project } from "../../lib/contracts";
import { importProjectUrl, type UrlImportRequest } from "../projects/api";
import {
  discoverOpportunities,
  type DiscoveryRequest,
  type DiscoveryResult,
  type SourceCandidate,
} from "./api";

const categories = [
  { id: "trending", label: "Trending", icon: "↗" },
  { id: "news", label: "News", icon: "◉" },
  { id: "movies", label: "Movies & TV", icon: "▶" },
  { id: "sports", label: "Sports", icon: "◇" },
  { id: "technology", label: "Technology", icon: "⌁" },
  { id: "podcasts", label: "Podcasts", icon: "◌" },
  { id: "gaming", label: "Gaming", icon: "✦" },
] as const;

export function TrendDiscovery({
  onCreated,
  loadOpportunities = discoverOpportunities,
  importSource = importProjectUrl,
}: {
  onCreated: (project: Project) => void;
  loadOpportunities?: (request: DiscoveryRequest) => Promise<DiscoveryResult>;
  importSource?: (request: UrlImportRequest) => Promise<Project>;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("trending");
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [selected, setSelected] = useState<SourceCandidate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function discover(
    event?: FormEvent<HTMLFormElement>,
    nextCategory = category,
  ) {
    event?.preventDefault();
    setBusy(true);
    setError(null);
    setSelected(null);
    try {
      setResult(await loadOpportunities({ query, category: nextCategory }));
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Topic discovery failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const project = await importSource({
        title: String(data.get("title")),
        url: selected.url,
        authorization_confirmed: data.get("authorization_confirmed") === "true",
      });
      onCreated(project);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Source import failed",
      );
    } finally {
      setBusy(false);
    }
  }

  const activeLabel =
    categories.find((item) => item.id === category)?.label ?? "Trending";

  return (
    <section className="discovery-workspace">
      <div className="discovery-search-panel">
        <form
          className="topic-search"
          onSubmit={(event) => void discover(event)}
        >
          <span aria-hidden="true">⌕</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search by topic"
            placeholder="Search a topic, person, show, or event…"
          />
          <button className="primary-button" disabled={busy}>
            {busy ? "Searching…" : "Discover videos"}
          </button>
        </form>
        <div className="topic-categories" aria-label="Browse categories">
          {categories.map((item) => (
            <button
              key={item.id}
              type="button"
              className={category === item.id ? "active" : ""}
              aria-pressed={category === item.id}
              onClick={() => {
                setCategory(item.id);
                void discover(undefined, item.id);
              }}
            >
              <span aria-hidden="true">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {result && (
        <>
          {result.topics.length > 0 && (
            <section className="trend-strip" aria-labelledby="trend-heading">
              <div>
                <span className="eyebrow">CURRENT SIGNALS</span>
                <h2 id="trend-heading">
                  {result.query ? `Related to “${result.query}”` : activeLabel}
                </h2>
              </div>
              <div className="trend-chips">
                {result.topics.slice(0, 6).map((topic) => (
                  <button
                    type="button"
                    key={topic.title}
                    onClick={() => {
                      setQuery(topic.title);
                      void loadOpportunities({
                        query: topic.title,
                        category,
                      }).then(setResult, (caught: Error) =>
                        setError(caught.message),
                      );
                    }}
                  >
                    <strong>{topic.title}</strong>
                    {topic.approximate_traffic && (
                      <small>{topic.approximate_traffic}</small>
                    )}
                  </button>
                ))}
              </div>
            </section>
          )}

          <section className="source-panel" aria-labelledby="source-heading">
            <div className="section-heading">
              <div>
                <span className="eyebrow">SOURCE IDEAS</span>
                <h2 id="source-heading">
                  {result.query
                    ? `Videos about ${result.query}`
                    : `${activeLabel} videos`}
                </h2>
              </div>
              <small>{result.note}</small>
            </div>
            {result.sources.length === 0 ? (
              <div className="empty-state compact">
                <h3>No recent videos found</h3>
                <p>Try a broader topic or another category.</p>
              </div>
            ) : (
              <div className="source-grid">
                {result.sources.map((source) => (
                  <article key={source.id} className="source-card">
                    {source.thumbnail_url ? (
                      // Provider thumbnails are remote, user-selected discovery content.
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={source.thumbnail_url} alt="" />
                    ) : (
                      <div className="source-placeholder" aria-hidden="true">
                        ▶
                      </div>
                    )}
                    <div className="source-card-copy">
                      <span className="source-kind">
                        {source.is_upcoming ? "Upcoming" : source.topic}
                      </span>
                      <h3>{source.title}</h3>
                      <p>
                        {source.channel ?? "Unknown channel"}
                        {source.view_count
                          ? ` · ${source.view_count.toLocaleString()} views`
                          : ""}
                      </p>
                    </div>
                    <div className="source-score" title="Opportunity score">
                      {source.source_score}
                    </div>
                    <div className="source-actions">
                      <a href={source.url} target="_blank" rel="noreferrer">
                        Preview ↗
                      </a>
                      <button type="button" onClick={() => setSelected(source)}>
                        Use video
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {!result && !error && (
        <div className="discovery-empty">
          <span aria-hidden="true">✦</span>
          <h2>Find ideas beyond your feed</h2>
          <p>
            Choose a category or search any topic. ReachCut will surface recent,
            publicly available source ideas for you to review.
          </p>
        </div>
      )}

      {selected && (
        <form
          className="discovery-import"
          onSubmit={(event) => void createProject(event)}
        >
          <div>
            <span className="eyebrow">CREATE PROJECT</span>
            <h2>Import selected source</h2>
            <p>{selected.title}</p>
          </div>
          <label>
            Project name
            <input
              name="title"
              defaultValue={selected.title}
              required
              maxLength={200}
            />
          </label>
          <label className="check">
            <input
              name="authorization_confirmed"
              type="checkbox"
              value="true"
              required
            />
            <span>
              I own, license, or have permission to repurpose this media.
            </span>
          </label>
          <div className="source-actions">
            <button type="button" onClick={() => setSelected(null)}>
              Cancel
            </button>
            <button className="primary-button" disabled={busy}>
              {busy ? "Importing…" : "Import and open project"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

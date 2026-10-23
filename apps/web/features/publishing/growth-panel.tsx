"use client";
import { useEffect, useRef } from "react";
import type { SocialAccount } from "../../lib/contracts";
import type { PlatformCopy } from "./growth-api";
import { GrowthDiagnosisList } from "./growth-results";
import { useGrowth } from "./use-growth";

export function GrowthPanel({
  clipId,
  autoApply = true,
  accounts,
  onApply,
  refreshKey,
}: {
  clipId: string;
  autoApply?: boolean;
  refreshKey?: string;
  accounts: SocialAccount[];
  onApply: (copy: PlatformCopy[]) => void;
}) {
  const growth = useGrowth(clipId, refreshKey);
  const { brief, setBrief } = growth;
  const applied = useRef("");
  useEffect(() => {
    if (autoApply && brief?.automatic && brief.creative) {
      const key = JSON.stringify(brief.creative.packages);
      if (applied.current !== key) {
        applied.current = key;
        onApply(brief.creative.packages);
      }
    }
  }, [brief, onApply, autoApply]);
  if (!brief)
    return (
      <section className="growth-panel">
        <h2>Audience & growth brief</h2>
        <p role={growth.error ? "alert" : "status"}>
          {growth.error || "Loading growth brief…"}
        </p>
      </section>
    );
  function patch(value: Partial<typeof brief>) {
    setBrief((current) =>
      current ? { ...current, ...value, automatic: false } : current,
    );
  }
  return (
    <section className="growth-panel" aria-label="Audience and growth brief">
      <h2>Audience & growth brief</h2>
      <p>
        AI infers the audience, selects a search query and opening, and prepares
        publishing copy using this clip and saved performance. Both project
        pipeline modes include this step automatically.
      </p>
      <p role="status">
        {growth.preparation?.status === "ready"
          ? "AI optimization ready. Publishing copy is applied automatically."
          : growth.preparation?.status === "manual"
            ? "Saved or localized publishing copy is ready. Your language-version settings are preserved."
            : growth.preparation?.status === "working"
              ? "AI is analyzing and optimizing this clip…"
              : growth.preparation?.status === "failed"
                ? "AI needs attention. Check Settings or retry."
                : brief.creative
                  ? "Saved growth brief available."
                  : growth.automaticEnabled
                    ? "AI preparation will start automatically."
                    : "Automatic growth is disabled in Settings."}
      </p>
      {brief.profile.audience && (
        <p>
          <strong>Audience:</strong> {brief.profile.audience} ·{" "}
          {brief.profile.language} · {brief.profile.country}
        </p>
      )}
      {brief.target_query && (
        <p>
          <strong>Search focus:</strong> {brief.target_query}
        </p>
      )}
      {growth.preparation?.reasoning && <p>{growth.preparation.reasoning}</p>}
      {brief.creative && (
        <p>
          <strong>Next experiment:</strong> {brief.creative.experiment}
        </p>
      )}
      <button
        type="button"
        disabled={
          growth.pending ||
          ["working", "pending"].includes(growth.preparation?.status ?? "")
        }
        onClick={() => void growth.optimize()}
      >
        {growth.preparation?.status === "failed"
          ? "Retry growth analysis"
          : "Refresh growth analysis"}
      </button>
      <details>
        <summary>Advanced audience, evidence & publishing copy</summary>
        <fieldset disabled={growth.pending}>
          <div className="growth-fields">
            <label>
              Learn from account
              <select
                value={brief.account_id ?? ""}
                onChange={(e) =>
                  patch({
                    account_id: e.target.value || null,
                    profile: growth.profiles[e.target.value] ?? brief.profile,
                    creative: null,
                  })
                }
              >
                <option value="">No account history</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label} · {a.platform}
                  </option>
                ))}
              </select>
            </label>
            {(
              [
                ["audience", "Target audience"],
                ["niche", "Topic focus"],
                ["language", "Content language"],
                ["country", "Target country"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  maxLength={
                    key === "audience" ? 500 : key === "niche" ? 200 : 100
                  }
                  value={brief.profile[key]}
                  onChange={(e) =>
                    patch({
                      profile: { ...brief.profile, [key]: e.target.value },
                      creative: null,
                    })
                  }
                />
              </label>
            ))}
            <label>
              Target search query
              <input
                maxLength={200}
                value={brief.target_query}
                onChange={(e) =>
                  patch({ target_query: e.target.value, creative: null })
                }
                placeholder="The specific question this clip answers"
              />
            </label>
          </div>
          <details>
            <summary>Search evidence ({brief.evidence.length})</summary>
            <p>
              Enter observations from tools such as TikTok Creator Search
              Insights. Queries without evidence are hypotheses; ReachCut does
              not measure search demand.
            </p>
            <a
              href="https://newsroom.tiktok.com/creator-search-insights?lang=en"
              target="_blank"
              rel="noreferrer"
            >
              About Creator Search Insights ↗
            </a>
            {brief.evidence.map((evidence, i) => (
              <div className="growth-evidence" key={i}>
                <label>
                  Search phrase
                  <input
                    maxLength={200}
                    value={evidence.query}
                    onChange={(e) =>
                      patch({
                        evidence: brief.evidence.map((v, n) =>
                          n === i ? { ...v, query: e.target.value } : v,
                        ),
                        creative: null,
                      })
                    }
                  />
                </label>
                <label>
                  Source URL
                  <input
                    type="url"
                    value={evidence.source_url}
                    onChange={(e) =>
                      patch({
                        evidence: brief.evidence.map((v, n) =>
                          n === i ? { ...v, source_url: e.target.value } : v,
                        ),
                        creative: null,
                      })
                    }
                  />
                </label>
                <label>
                  Observed on
                  <input
                    type="date"
                    value={evidence.observed_at.slice(0, 10)}
                    onChange={(e) =>
                      patch({
                        evidence: brief.evidence.map((v, n) =>
                          n === i
                            ? {
                                ...v,
                                observed_at: `${e.target.value}T00:00:00Z`,
                              }
                            : v,
                        ),
                        creative: null,
                      })
                    }
                  />
                </label>
                <label>
                  What you observed
                  <textarea
                    maxLength={1000}
                    value={evidence.notes}
                    onChange={(e) =>
                      patch({
                        evidence: brief.evidence.map((v, n) =>
                          n === i ? { ...v, notes: e.target.value } : v,
                        ),
                        creative: null,
                      })
                    }
                  />
                </label>
                <button
                  type="button"
                  onClick={() =>
                    patch({
                      evidence: brief.evidence.filter((_, n) => n !== i),
                      creative: null,
                    })
                  }
                >
                  Remove observation
                </button>
              </div>
            ))}
            <button
              type="button"
              disabled={brief.evidence.length >= 20}
              onClick={() =>
                patch({
                  evidence: [
                    ...brief.evidence,
                    {
                      query: brief.target_query,
                      source_url: "",
                      observed_at: new Date().toISOString(),
                      notes: "",
                    },
                  ],
                  creative: null,
                })
              }
            >
              Add search observation
            </button>
          </details>
          <div className="inline-actions">
            <button type="button" onClick={() => void growth.run("generate")}>
              {growth.pending ? "Working…" : "Generate growth draft"}
            </button>
            <button type="button" onClick={() => void growth.run("save")}>
              Save brief & audience
            </button>
          </div>
          {brief.creative && (
            <>
              <h3>Opening experiments</h3>
              <p>
                Suggestions for your next edit. Review factual accuracy before
                changing the video in Studio.
              </p>
              <ol>
                {brief.creative.openings.map((opening, i) => (
                  <li key={i}>
                    <strong>{opening.opening_line}</strong>
                    <p>First frame: {opening.first_frame}</p>
                  </li>
                ))}
              </ol>
              <label>
                Next experiment
                <textarea
                  maxLength={1000}
                  value={brief.creative.experiment}
                  onChange={(e) =>
                    patch({
                      creative: {
                        ...brief.creative!,
                        experiment: e.target.value,
                      },
                    })
                  }
                />
              </label>
              <h3>Platform publishing copy</h3>
              {brief.creative.packages.map((copy, i) => (
                <details key={copy.platform}>
                  <summary>
                    {copy.platform} · {copy.title}
                  </summary>
                  {(
                    [
                      ["title", "Title"],
                      ["caption", "Caption"],
                      ["cover_text", "Cover text suggestion"],
                    ] as const
                  ).map(([key, label]) => (
                    <label key={key}>
                      {label}
                      <textarea
                        maxLength={key === "caption" ? 2000 : 100}
                        value={copy[key]}
                        onChange={(e) =>
                          patch({
                            creative: {
                              ...brief.creative!,
                              packages: brief.creative!.packages.map((p, n) =>
                                n === i ? { ...p, [key]: e.target.value } : p,
                              ),
                            },
                          })
                        }
                      />
                    </label>
                  ))}
                  <label>
                    Hashtags (space separated)
                    <input
                      value={copy.hashtags.join(" ")}
                      onChange={(e) =>
                        patch({
                          creative: {
                            ...brief.creative!,
                            packages: brief.creative!.packages.map((p, n) =>
                              n === i
                                ? {
                                    ...p,
                                    hashtags: e.target.value
                                      .split(/\s+/)
                                      .filter(Boolean)
                                      .slice(0, 5),
                                  }
                                : p,
                            ),
                          },
                        })
                      }
                    />
                  </label>
                </details>
              ))}
              <button
                type="button"
                onClick={() =>
                  void growth.run("save").then((saved) => {
                    if (saved?.creative) onApply(saved.creative.packages);
                  })
                }
              >
                Use reviewed copy in publisher
              </button>
            </>
          )}
        </fieldset>
      </details>
      {growth.error && (
        <p role="alert" className="error">
          {growth.error}
        </p>
      )}
      {growth.message && <p role="status">{growth.message}</p>}
      <GrowthDiagnosisList rows={growth.diagnoses} />
    </section>
  );
}

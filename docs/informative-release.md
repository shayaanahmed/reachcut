# ReachCut release: source videos and informative shorts

## Navigation and compatibility

The two main entry points are **Clip a video** (`/projects/new`) and **Create a short** (`/create`). **Source videos** keeps `/projects` and existing clip/editor/publishing URLs. **Created videos** (`/created`) lists informative drafts and completed exports. **Video styles** edits user-defined content-series formats and thumbnail identities. Niche purpose, audience, voice and branding are saved for reuse.

**Labs → AI scenes** (`/labs/ai-scenes`) contains the experimental cinematic generator and its existing library. `/generate`, `/stories` and `/stories/:id` remain usable. Existing reference uploads, recovery, downloads and videos are preserved. References guide style; they do not guarantee motion, physics, editing or audience performance.

## Clipping and review

The durable stages inspect media, sample scenes/faces/motion, transcribe, select moments, render previews, and review available evidence. Missing audio skips transcription. Silent sources use motion signals when available; these selections explicitly require human editorial review. Tracking failure preserves a wider default composition and keeps diagnostics available. Scene cuts are histogram-based estimates at the configured sample interval.

Retries reuse matching plans and clips, preserving clip IDs, edits, exports and publication history. Cache inputs include media identity, transcription language/model, editorial model, visual artifacts, source context and selection settings. Tracking identity includes sampling settings. Stage JSON writes are atomic; corrupt JSON is rebuilt. Preview caches check referenced files. A stage can be retried through `POST /api/projects/:id/stages/:stage/retry`; downstream stage keys are cleared. Previously saved results remain available for recovery.

Review combines transcript-boundary findings, caption artifact timing/layout estimates, stream/duration checks and a full rendered-media decode with silence detection. One supported correction per clip can reduce an estimated oversized caption layout or rerender invalid media. Remaining findings and correction history are available in **Quality review findings** and the stage artifact. Caption layout estimation is not pixel-level overflow detection. Semantic framing, sentence meaning, subtitle shaping, pronunciation and factual accuracy still require human preview review. Editorial scores estimate suitability; they do not predict audience performance.

## Advanced informative creation

The default `/create` workflow is described in [Guided short creation](guided-creation.md). The following workflow remains available at `/created/advanced` for existing researched videos and manual assets.

1. Choose a channel preset, category, style, topic, language and 30–60 second target. A custom topic needs no discovery step.
2. Enter reliable HTTPS source URLs. The server retrieves bounded HTML excerpts from configured hosts; redirects are rejected. Review sources and retrieval dates. Local Ollama can draft the script, or write it manually. Edit sections and attach exact source excerpts to claims. Interpretations, disputed assertions and missing evidence block script approval in this release.
3. Approve the saved script and evidence. Script, source or language/settings changes require renewed approval. Unsaved script edits disable approval and production in the UI.
4. Use a saved Voicebox voice or upload narration **for each script section**. This is a complete alternative for unavailable languages. Upload real screenshots, illustrations, maps and recordings. Essential screenshot/recording/map requirements block production if missing. Explanation cards require explicit opt-in and an explanation-compatible visual plan. They are labeled explanations, not software proof or archival evidence. There is no dependency on cinematic generation.
5. Production measures each audio section and uses it for scene timing. Locally installed Whisper can match measured ASR word timings to the display script. When recognition differs or the model is unavailable, phrase timing is approximate and human review is required. Overlong narration fails with a request to shorten/reapprove; it is never silently truncated. Total narration must reach 30 seconds and remain within the chosen target plus three seconds (maximum 60.5 seconds for container tolerance).
6. Review the vertical preview, findings, source coverage, asset credits and pronunciation. Download the clean master and provenance JSON. Approval creates an immutable managed publishing revision compatible with existing destination selection and metrics. Previous approved revisions and publishing history remain intact after later edits.

Uploads are capped at 200 MB per section asset. Audio, image and recording assets are decoded/inspected before use. Usage rights default to **unknown**. Save attribution, origin and synthetic classification; supplied attribution is included in the rendered video and provenance response. No blanket rights assurance is made. The master has no ReachCut or destination watermark, music or effects that can overpower narration. Platform-specific metadata remains editable in the existing publishing screen. Use destination disclosure controls when applicable; automatic synthetic-content disclosure is not implemented.

Section audio, measured timing, Voicebox generation ID, voice/model/settings and visual provenance are durable. Replacing a visual rebuilds its scene and final assembly while reusing unrelated narration and scenes. Regenerating a voice section keeps the other sections. Stops are checked between operations and while polling Voicebox; an in-progress FFmpeg operation completes before the stop is handled. A shared process/thread hardware reservation serializes narration and AI-scene jobs across ReachCut workers. It cannot reserve hardware used by unrelated applications.

## Voicebox setup

Run Voicebox separately with its own dependencies, models and voice profiles. ReachCut does not import its model stack or change that repository. Configure:

```dotenv
CLIPPER_VOICEBOX_BASE_URL=http://127.0.0.1:17600
CLIPPER_VOICEBOX_TIMEOUT_SECONDS=600
```

The default Voicebox port is 17600; set `CLIPPER_VOICEBOX_BASE_URL` if your server uses another port. Settings shows connection state, profiles, engine models, installation status and the inspected registry's languages. Save the default profile, engine, audience, tone, language, caption font and pronunciation corrections in a channel preset. Video overrides do not change the preset. Source video imports can also select a preset: the job inherits its language and snapshots caption font/accent so later preset changes do not change existing work. Delivery instructions are exposed only for an engine whose inspected registry supports them.

Voicebox currently does not expose its per-engine language registry over HTTP. ReachCut maintains an explicit manifest from the inspected backend registry and intersects it with `/models/status`; unknown models fail closed. Reinspect `backend/backends/__init__.py`, request schemas and routes when upgrading Voicebox. Registry support is not a listening-quality certification.

The adapter uses `GET /health`, `/profiles`, `/models/status`, `POST /generate`, `GET /history/:id`, `GET /history/:id/export-audio`, and `POST /generate/:id/cancel`. Generation IDs are saved before polling and completed audio is copied through HTTP into ReachCut artifacts. Retries resume the same accepted generation. A submission interrupted before its ID is saved is marked uncertain: reconcile the matching generation ID from Voicebox history rather than blindly resubmitting. The recovery endpoint checks text, profile, engine and language association. A ReachCut stop and confirmed upstream cancellation are recorded separately. Install models explicitly in Voicebox before generating; ReachCut does not call download endpoints.

**Urdu and Urdu-English narration are unverified and disabled through Voicebox. Hindi is never substituted. Use uploaded narration. English has adapter fixture coverage; real Voicebox English output still needs verification with a running service.** Separate language support does not establish fluent code switching.

## Research, scripting and provider readiness

```dotenv
CLIPPER_RESEARCH_ALLOWED_HOSTS=docs.python.org,openai.com,learn.microsoft.com,support.google.com,ncbi.nlm.nih.gov,pmc.ncbi.nlm.nih.gov,loc.gov,archives.gov,si.edu
CLIPPER_RESEARCH_SEARCH_URL=
```

Add the primary/authoritative hosts you intend to use. Retrieval is an excerpt of a web page, not a fact-checking verdict; PDF extraction, paywalls, browser-only sources and redirects are not supported. Claim quote containment establishes traceability only. A person must inspect whether the quote actually supports the claim. Retrieved/provider text is untrusted data; provider output is schema-validated before use.

Optional topic suggestions use a configured SearXNG-compatible JSON search endpoint (`q`, `format=json`, `results[].title/url`). Search results are suggestions, never labeled trending. The guided flow separately samples dated YouTube references for directional niche comparisons; see its documented limits. Custom topics and direct source entry work without search.

Scripting uses the saved Ollama URL and model from Settings, sends schema instructions in JSON mode and validates the result with Pydantic. JSON mode is documented in the [official Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md?plain=1). A real local test found this installation rejects the full script schema grammar; JSON mode avoids that runtime failure while retaining application validation. Model output can still contain inaccurate quotes; these are surfaced and block approval. Review and repair them in the claim editor.

Whisper model loading is local-cache-only. Install its model explicitly using the documented model setup commands. English-only Whisper models must not be used for Urdu quality verification. Mixed Urdu-English source transcription uses automatic language detection with a multilingual prompt. Unicode captions are shaped by libass; use a font containing the required glyphs.

Only free local narration/scripting, uploaded assets and deterministic explanation rendering are registered for this workflow. Research, script and narration interfaces allow adapters to be supplied; hosted narration, paid visual generation and semantic AI review are not configured implementations. Provider fees are $0 for these registered local adapters. Runtime estimates are unavailable; estimated cost and actual cost/duration are kept separately. Narration attempts are limited to 1–3 per unchanged section, default two; explicit spend settings do not authorize an unregistered paid provider.

## Publishing and recovery

Queued and direct uploads reserve a clip/account destination and atomically claim it before the outbound call. Published/processing reservations prevent duplicate retries. `uploadLimitExceeded` is a **YouTube channel restriction**, separate from `quotaExceeded`/`dailyLimitExceeded` Google Cloud quota. Both defer the destination; channel restrictions pause further queued uploads for that account. No reset time is invented. Check the provider, then deliberately remove the deferred attempt to authorize a retry. Uncertain network outcomes retain the destination reservation and require checking the platform before another upload. Other destinations keep their independent success/history.

Existing explicit automation approval behavior is preserved. Informative shorts require script approval before production and a separate final video approval before publishing. Metrics are those supplied by the existing providers; no unavailable retention data or causal learning claims are added. Informative records keep topic, category, style, opening script and the publishing project association for comparison; an automated experiment-analysis dashboard is not implemented.

## Migration, backups and rollback

This release adds `informative_shorts`, `channel_presets` and `publication_options` through the existing repeatable `Base.metadata.create_all` startup migration. Existing tables and columns are unchanged; old records need no backfill. Back up the database, credential store and complete data directory together before upgrading. Stop all API workers and schedulers while making a SQLite backup; copying only the database during active WAL writes is not a consistent backup. Do not remove old projects, source files, exports or Voicebox history as part of migration.

To roll back, stop workers, return to the previous application revision and retain the data directory and the new tables. The old application ignores additive tables. New queued uploads save privacy settings in the additive options table and resume after restart; old queued records without those settings require manual review so privacy is never guessed. Processing uploads with unknown outcomes are never automatically repeated. New informative work will not be scheduled by the old revision. Keep its artifacts for a later upgrade. Do not restore only a database backup while deleting media created since that backup. A full restore replaces the corresponding database and artifact snapshot together. Publishing outcomes are external and cannot be undone by restoring a database.

On the verification machine the bundled ffprobe marked arm64 actually contains an x86 binary. Metadata inspection falls back to already-installed PyAV when execution is incompatible. FFmpeg full decode and rendering remain separate checks. Prefer installing a native ffprobe for consistent behavior in all legacy media tools.

## Verification status

See [the release verification report](release-verification.md) for actual commands and media runs. Fixture orchestration is not proof of factual, editorial, speech or visual quality. Do not treat this document as a declaration that every requested release acceptance path has passed.

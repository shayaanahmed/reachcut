# ReachCut release verification — 17 October 2026

Status: **working release candidate; full release acceptance is not complete**.

The implementation connects source-video clipping, informative drafts/production, Voicebox HTTP narration, channel presets, review findings, immutable approved publishing revisions, durable recovery and destination restrictions. The workflow and migration details are in [the release guide](informative-release.md). Existing API/database names and legacy Labs routes are preserved.

## Voicebox verification update — 20 October 2026

The real service is healthy at `http://127.0.0.1:17600`, with Qwen TTS 1.7B loaded on CPU and two saved voice profiles. The project default incorrectly used port 17493; it now uses 17600, matching `.env.example`. Restart an already-running ReachCut API to load the new default. `CLIPPER_VOICEBOX_BASE_URL` still overrides it.

The actual `VoiceboxNarrationProvider` validated an English profile, submitted “This is a ReachCut voice-over connection test.”, polled generation `d473a8f4-8a12-4e9c-a5fa-72e2a241dc80` to completion, and downloaded 157,484 bytes of WAV audio. The file measured 3.28 seconds, decoded successfully, and contained a non-silent audio signal. That file was then attached through `ClipService` to an isolated uploaded clip and rendered into a 1080×1920 MP4 with audio. No live project, publishing destination, voice profile, or model installation was changed. Temporary audio: `/tmp/reachcut-voicebox-smoke.wav`.

This verifies English generation, polling, retrieval, decoding, and clip mixing/export. It does not establish pronunciation quality, other languages, or live cancellation/recovery; those recovery paths retain automated fixture coverage. Urdu/Urdu-English generation remains disabled. Clip Studio currently accepts uploaded voice-over files; direct text-to-speech controls exist in the generated-short narration workflow, not the uploaded-clip editor. Saved LuxTTS and Chatterbox model selection was also corrected in all narration pickers.

## Automated checks

| Check | Result |
| --- | --- |
| `pnpm check` | Passed: Ruff lint/format, strict mypy, ESLint, Prettier, TypeScript |
| `pnpm test` | 282 API tests and 70 frontend tests passed |
| Browser suite | 9 tests passed with installed Google Chrome; publishing side effects mocked |
| `pnpm --dir apps/web build` | Production build passed |
| `git diff --check` | Passed |

The commands used `UV_CACHE_DIR=/tmp/reachcut-uv-cache` because the normal uv cache is outside the writable sandbox. No dependency/model download was needed. Playwright's pinned browser revision was absent, so browser tests used the already-installed Chrome executable through `PLAYWRIGHT_EXECUTABLE_PATH`. One existing FastAPI/HTTPX deprecation warning remains.

New tests cover existing-table compatibility and repeatable additive migration, exact claim evidence, invalid structured scripts, script approval/invalidation, queued edit guards, uploaded narration, measured section timing, local ASR alignment mapping, partial cache reuse, bounded correction and unresolved findings, interrupted generation/recovery, unconfirmed upstream cancellation, Voicebox installation/language/profile/delivery capabilities, HTTP audio retrieval and offline failures, attempt budgets, privacy-preserving publication recovery, channel upload restrictions, destination reservations/claims and unavailable preset destinations. Existing tests continue to exercise approvals, URL import, editing, exports, automation and publishing/metrics isolation.

## Real service and media runs

| Run | What actually happened | What it does not establish |
| --- | --- | --- |
| English clipping | Generated a 32-second English speech source locally with the installed macOS voice, transcribed with the already-cached `small.en` Whisper model, selected a clip through real local Ollama, rendered its preview, edited caption style, approved and exported a 9.8 MB final file. A retry retained the original clip. | Real-world editorial quality across diverse sources or Urdu recognition |
| Supplied YouTube URL | The actual ReachCut yt-dlp adapter downloaded `https://www.youtube.com/watch?v=ncoIUi_Wzh4`: **61 Surah Saff Dr Israr Ahmed Urdu**, 103,914,423 bytes, 1280×720, audio present, 2,038.221 seconds. A manual 60–90 second interval was exported as a 30-second vertical clip and passed decode/stream/duration/audio checks. | Automated Urdu transcription and editorial selection; the interval was manually chosen for media execution testing |
| Source retrieval and scripting | Retrieved the official Python data-structures documentation and drafted a script using installed local `qwen3:8b-q4_K_M`. Application validation found two inaccurate source quotations and surfaced them as approval-blocking findings. | A fully approved, factually reviewed, AI-produced research video |
| Uploaded narration and three style branches | Produced three 32.125-second vertical masters with uploaded English speech through the tech/demo, psychology/explainer and history/timeline production branches. Full decode passed and each could be handed to the managed publishing workspace after test approval. | Psychology/history research quality: all three used clearly identified media fixture content, not separately researched genre scripts |
| Mixed-script captions | Rendered and visually inspected English/Urdu text. A real render exposed and led to a fix for empty captions on cues without word timings. | Urdu or Urdu-English TTS pronunciation, naturalness, complete font coverage or pixel-perfect captions for every input |
| Existing legacy story | Read an existing completed four-scene story from the real database through a read-only session, then opened its actual API response through Labs in Chrome and verified its legacy workspace and download link. The separate browser check passed without modifying the record. | A new cinematic generation run |
| Publishing | Upload-limit, duplicate-prevention, privacy recovery and destination isolation were tested with fake publishers and browser interception. | Any real platform upload, disclosure submission or live metric sync |

The informative renders used real FFmpeg and real uploaded speech, not mocked encoded media. The narration came from the local system voice and was **not generated by Voicebox**. These runs are execution checks, not a listening-quality certification. Fixture orchestration tests remain clearly separate from real media execution.

Temporary review artifacts:

- English clipping export: `/tmp/reachcut-clipping-e2e/projects/fixture/source/clips/7269c5d7-9bbe-423a-afe8-969a74a8f618/final.mp4`
- Imported Urdu manual excerpt: `/tmp/reachcut-url-import/manual-urdu-excerpt.mp4`
- Imported original: `/tmp/reachcut-url-import/source/source.mp4`
- Informative style masters and immutable publishing copies: `/tmp/reachcut-e2e/`
- Source extraction and actual model script/findings: `/tmp/reachcut-real-research.json`
- Creation-screen visual inspection: `/tmp/reachcut-create-screen.png`

Tests and real media runs used isolated temporary databases/directories. No public publishing, unapproved provider spend, large-model download or Voicebox repository modification occurred.

## Remaining acceptance blockers and limitations

**The original 17 October check found Voicebox offline at `http://127.0.0.1:17493`.** The 20 October update above supersedes that connection result and verifies the English media path on port 17600. Real cancellation/recovery and human listening acceptance remain open; adapter fixtures are not proof of narration quality.

**A multilingual Whisper model is not cached on this machine.** The configured `large-v3-turbo` therefore cannot process the supplied Urdu lecture without explicit external setup. The cached `small.en` model was used only for English. Automatic Urdu clipping remains unverified; the successful URL download and manual render do not replace that test.

**Urdu and Urdu-English Voicebox narration remain unverified and disabled.** No listening review has certified them. Uploaded narration remains a usable alternative. Hindi is not substituted.

**The three category workflows still need separate real research/editorial/media acceptance runs.** The three rendered style fixtures verify execution, not the factual quality of tech, psychology or history content. The real tech model draft correctly stopped at invalid evidence instead of proceeding through false approval.

Deterministic review supports rendered full decode, streams, duration and silence, plus caption artifact timing and conservative layout estimates. It does not inspect semantic framing or perform pixel-level caption overflow detection. Human preview review is required. Explanation cards and supplied visual assets are functional; a hosted image/video-generation adapter, automated synthetic-disclosure submission, dated trend ranking and an experiment-analysis dashboard are not implemented. The available local providers do not incur provider fees; unavailable time/cost information is not invented.

Full release acceptance must remain open until the blocked real narration and multilingual paths, category-specific quality review, and a final human media/listening review are completed.

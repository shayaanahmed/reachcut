# Short studio

`/create` offers two paths, with no niche setup:

1. **Exciting GitHub repos:** paste a public repository root URL. ReachCut reads its metadata and README without cloning or executing code. Local Ollama analyzes its actual purpose, useful possibilities, working principles and prerequisites, then proposes three storylines for both developers and ordinary people.
2. **Tech tricks:** ask Ollama for ideas, optionally adding a focus. ReachCut reads current official Microsoft, Apple and Google feature guides before Ollama develops three practical storylines. Suggestions are grounded in these guides; they are creative choices, not measured popularity rankings.

Choose a pictorial storyline card, then let AI select six frames or choose them manually. The manual picker has four starting presets, six scene slots and one animated preview with an explicit selected badge. Ollama writes a complete six-beat story before designing any frames: hook, purpose, example, action, outcome and an accessible closing question. A separate editorial pass checks facts, evidence, repetition and incomplete sentences and requests corrections. Verification classifies findings: unsupported claims and incomplete sentences remain blocking; repetition is retried, then saved as a visible editing suggestion if it persists. Repetition alone cannot discard a storyboard or block its approval. Screen copy is then designed around those approved beats and reviewed again. Review the storyboard and create the video, or regenerate with feedback. A new storyboard preserves the previous draft. Research and planning are background tasks: progress, inputs and research are saved, retries are idempotent, and interrupted work is marked retryable after a restart. Inputs and preview browsing stay available during work; duplicate submissions are guarded without a page-wide waiting cursor. The status panel distinguishes writing, source review, corrections and scene design.

## Frame library

`/frames` contains only the 24 designs from the supplied **Faceless frame library, vol. 2** and **vol. 3** documents. The previous catalogue and sequences are retired from browsing and new creation.

Volume 2 contains Before / after, Versus, Leaderboard, Code diff, Language bar, Notification toasts, Contributors, Timeline, Hot take, Build progress, File tree and Speed dial. Its seven themes are Neon Violet, Paper Pop, Sunset Gradient, Terminal Cyan, Amber Cards, Glass Light and Mono Teal.

Volume 3 contains Kinetic poster, Newspaper front page, Chat thread, Code editor window, Retro CRT, Trading card, Receipt, Blueprint, Sticker pack, Pull request, Story poll and Bento stats. Each keeps its own design language. Two reference defects are corrected: the blueprint grid background and the trading card's overflowing illustration height.

The gallery opens on individual animated frames, with collection, search and story-beat filters. Click or keyboard-activate a frame to replay; Replay all restarts the gallery. Four six-scene sequences cover all 24 designs. Volume 2 theme choices carry into the saved storyboard and production, while volume 3 retains its individual styles.

Previews preserve the reference documents' illustrative placeholder copy and numbers. Production binds source-grounded story content into the original HTML and uses the same CSS animation as the gallery. It never treats a sample number, fake social notification, code snippet or poll percentage as evidence about a real tool. Unquantified graphs remain schematic. Original reference files and extracted designs live in `apps/api/src/clipper/rendering/assets/frames/library/`.

Saved videos retain their snapshotted composition and theme. Retired frame types are still readable for existing video snapshots but cannot be selected for new storyboards.

## Production and voice

New videos default to a 30-second captioned video with an original synthesized sound bed. Native Ollama generates the story and screen copy; Chromium/FFmpeg animate and assemble 1080×1920, 30fps video. No video diffusion service is required. The selected sequence, story, evidence and frame content are snapshotted with the video. Captions remain short and separate from narration.

VoiceBox is optional. Run it separately, install a model and create a profile, then choose a voice in storyboard review or add it later from Created videos. Narrated scenes extend to fit speech rather than truncating it; short speech is padded to the scene's intended duration. The existing 60-second overall production limit still applies.

Scene timing follows the script while preserving the 30-second target and a brisk opening. The configured local vision model checks generated photographs for relevance and obvious defects, with one automatic replacement attempt. Music-only cuts have an explicit review notice. Older studio drafts must be regenerated through the editorial checks before production or publishing. These checks catch concrete defects; they do not predict virality or replace watching the final video.

Finished videos stay in Created videos. Open Change frames to create a separate editable version with the existing narration and voice settings, using AI or manual frame choices. Videos can be deleted with an inline confirmation; active renders must finish or be stopped first, and separately published project copies are kept. Finished videos also continue through the existing clip editor, export and publishing workflow. Existing video snapshots and assets remain readable. The saved niche CRUD, niche-specific template generator, font-look generator, single-composition preset catalog and associated UI were removed. Old `/video-styles` and `/created/advanced` links redirect to the replacement pages. The previous cinematic creation wizard was also removed; historic AI-scene jobs retain their recovery support.

## Setup and checks

Configure the Ollama host and text model in Settings. The supplied frames need no image-generation model. VoiceBox is needed only for narration. FFmpeg is required for assembly. After syncing API dependencies, run `uv run --project apps/api python -m playwright install chromium` for the HTML frame renderer. The Docker image installs Chromium and its system dependencies during its build. Private repos, moved repos, unreadable documentation, GitHub rate limits and failed official-guide retrieval produce actionable errors rather than fabricated source material.

`pnpm check` runs lint, formatting and type checks. `pnpm test` covers grounded planning, durable retries, source URL validation, immutable episodes, real frame rendering, short production and clip compatibility. Browser checks cover both creation paths, frame browsing, storyboard review and mobile layout. Ollama output quality also requires a live local-model check.

## GitHub storyboard-first flow

New GitHub requests use `flow: "storyboard"`: the repository URL produces a complete five-scene story before template selection. The saved brief retains narration, captions, visual directions and editorial notes. Selecting a compatible template reuses that story; `auto_produce: true` approves the reviewed script and queues rendering. Tech-trick and older saved tasks retain their existing flow.

After rendering, a local vision model inspects two timestamped frames from every scene of the final cut, along with the approved narration and timings. Its assessment covers the hook, clarity, pacing and shareability. Automatic refinement can shorten existing captions, titles or eyebrows while preserving factual qualifiers; it never rewrites approved narration or changes the selected template. Up to two refinements are rendered and reviewed again. Remaining blockers or an unavailable reviewer hold publishing and remain visible for correction or retry. A passing assessment is tied to the exact output file hash. The final human approval remains required. Shareability scores are editorial judgments, not guarantees of virality or evidence of a current trend.

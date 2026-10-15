# Local story-to-video studio

ReachCut's Story Studio is a fully local orchestration layer. It does not call EveryGen or
another hosted video API.

## Pipeline

1. Ollama turns a rough idea or complete story into a schema-validated character bible and
   scene plan.
2. The user reviews the characters, story beats, camera moves, narration, and seeds before
   any expensive render starts.
3. Lightricks' official LTX Desktop backend renders every scene locally with LTX 2.5 Fast.
4. An optional uploaded character image conditions the first shot. ReachCut extracts the
   final frame of each scene and feeds it into the following scene for visual continuity.
5. FFmpeg concatenates the generated video and synchronized audio into a web-optimized MP4.
6. Failed jobs retain completed scenes and can resume at the first missing scene.

## One-time setup

```bash
pnpm video:setup
pnpm video:engine
pnpm dev
```

Open `/generate`. The readiness panel checks Ollama, the LTX worker, Hugging Face model
authorization, and model downloads independently. LTX 2.5 weights are license-gated; use the
panel to authorize Hugging Face, accept the LTX 2.5 license, and start the model download.

The official core pack currently needs roughly 72 GB of disk space. Draft mode renders at
540p. Final mode requests native 1080p from LTX and uses the same scene/continuity pipeline.

## Local services

- ReachCut API: `127.0.0.1:8000`
- ReachCut web: `127.0.0.1:3000`
- Ollama: `127.0.0.1:11434`
- LTX worker: `127.0.0.1:41954`

The LTX worker uses a local bearer token and listens on port `41954` so both a native API and
the Docker API can reach it. Its environment, models, logs, and outputs live under
`apps/api/data/local-video/`, which is excluded from Git. If ReachCut is running natively and
you want loopback-only access, start it with
`CLIPPER_VIDEO_ENGINE_BIND_HOST=127.0.0.1 pnpm video:engine`.

## Reference template library

The reference library on `/generate` lists 346 public Everygen Shorts Studio clips from a
gallery snapshot taken on 2026-10-13. The four initial references appear first. Source names
and format hints are catalogue metadata, not AI classifications. No videos are downloaded
until **Save & classify** or an explicit import.

1. Preview a catalogue clip, import a Viewmax shorts MP4 URL, or upload your own MP4.
2. Click **Save & classify**. ReachCut saves the clip and samples eight chronological JPEG
   frames. Your configured thumbnail vision model in Ollama extracts a validated blueprint:
   format, tags, visual style, camera, inferred pacing, story structure, visible caption style
   and suitable subjects. Classifications retain the model name and survive restarts.
3. Select **AI chooses for my prompt** or click **Use template** on a classified clip.
4. Enter a prompt and create a story or storyboard. The editorial model selects among ready
   templates, explains its choice, and uses the blueprint to direct an original storyboard.
5. Review the storyboard and generate through the existing local LTX pipeline. Scene prompts
   persist the direction, so queued jobs and resumed renders do not need to reclassify a clip.

Classification requires a vision-capable Ollama model configured in Settings. Failed attempts
retain the clip and offer a retry; unclassified or failed references cannot be selected by AI.
Matching uses bounded batches of 20 candidates and compares batch winners for larger libraries.
Clips and atomic JSON metadata are stored in `data/reference-templates/`. The catalogue is
bundled in `generation/assets/reference_catalogue.json`; remote imports allow only HTTPS
URLs in `media.viewmax.io/static/prompt-library/shorts/`, with public DNS validation and no
redirects. Uploads and downloads are limited to 50 MB and three minutes.

The first version analyzes images, not audio. Pacing and story structure are inferred from
sampled frames. Caption styles are descriptive metadata; text overlays are not applied by
this generation flow. The renderer still uses five-second scenes, and matching a reference
does not reproduce its exact motion or editing.

To save and classify the complete catalogue in a resumable batch, run
`pnpm templates:import` while the local API and Ollama are running. Downloads use four
workers; vision classification runs sequentially. Completed clips are skipped when rerun.
Progress and errors are checkpointed in `data/reference-template-batch.json`.

## Continuous action and narration

Fixed-camera actions and hydraulic-press, CCTV, doorbell and bodycam formats use native
ten-second shots where possible. A ten-second continuous action is one generated clip;
a longer request uses ten-second chunks and an optional five-second remainder. Story scenes
remain available explicitly. The studio starts at ten seconds so a first test is inexpensive.

Spoken narration is off by default. Turn it on in the studio when a narrator is wanted.
Physical-action prompts describe contact and causality, and fixed-camera requests keep a
static camera setting. These controls improve direction; template matching currently passes
text instructions, not the source video's motion as a conditioning signal. Generated physics
and material behavior still require visual review. An uploaded opening frame can anchor
composition for the first shot.

# ReachCut

ReachCut is a local-first application for turning media you are authorized to repurpose into reviewable vertical clips. The core pipeline uses local models and local FFmpeg processes. Official API adapters can upload approved clips to YouTube, TikTok, Instagram Reels, Facebook Reels, and X without opening each platform's upload interface.

The current vertical slice provides secure local upload and allowlisted URL import through `yt-dlp`, media probing, durable stage state, provider-based `faster-whisper` transcription, Ollama/Qwen editorial selection, and schema-validated views- and revenue-oriented editing plans. The Creative Studio adds auto-curated source slices, content modes, OpenCV face/action tracking, caption presets and translation, hook/CTA/card overlays, transitions, zoom/progress effects, gameplay split-screen, B-roll, reaction PIP, SFX, music, and alternate source-audio selection. Deterministic FFmpeg rendering produces review previews and final 9:16 exports. Human approval is required before final rendering.

For Urdu and other non-English media, select the spoken language before analysis. The default `large-v3-turbo` Whisper model substantially improves multilingual recognition, while ASS/libass captions preserve Unicode/RTL shaping. Caption position, font, size, colors, highlighted words, line length, and pop/karaoke animation can be reviewed and changed on each generated clip.

Caption translation uses the configured local Ollama model and can render either the
translation or both languages. Visual tracking runs locally through OpenCV. Uploaded
gameplay, B-roll, reaction, sound, and music assets are copied into the clip's private
artifact directory; only attach media you own or are licensed to reuse.

> Importing a publicly accessible URL does **not** grant permission to republish it. Only process media you own, license, or have explicit authorization to repurpose.

## Prerequisites

- Python 3.13 (Python 3.12 is also supported; Python 3.14 is excluded for native ML compatibility)
- `uv`
- Node.js 22 LTS or newer and `pnpm`
- FFmpeg and ffprobe 7 or newer
- Ollama with a suitable instruction model, such as `qwen3:8b-q4_K_M`

## Development

### Docker Compose

The fully containerized CPU setup needs only Docker Desktop or Docker Engine with Compose:

```bash
cp .env.example .env
docker compose -f compose.yaml -f compose.ollama.yaml --profile setup run --rm model-init
docker compose --profile setup run --rm whisper-model-init
docker compose -f compose.yaml -f compose.ollama.yaml up --build -d
```

Open [http://localhost:3000](http://localhost:3000). The first command explicitly downloads the configured editorial model into a persistent Docker volume. Whisper downloads its configured model on the first transcription and caches it in a separate volume. Application projects and exports persist in `clipper-data`.

The API image includes the locked `yt-dlp` package. For native development, `CLIPPER_YT_DLP_REPOSITORY=../yt-dlp` runs the sibling checkout directly; clear that setting to use the installed package. URL import accepts HTTPS links from `CLIPPER_YT_DLP_ALLOWED_HOSTS` and always requires rights confirmation.

```bash
docker compose -f compose.yaml -f compose.ollama.yaml logs -f
docker compose -f compose.yaml -f compose.ollama.yaml down
```

On Apple Silicon, run Ollama natively to retain Metal acceleration, then use `docker compose up --build -d`; the API container reaches it through `host.docker.internal`. For an NVIDIA-backed Ollama container, append `-f compose.nvidia.yaml`. See [docs/docker.md](docs/docker.md) for volume backups, model changes, troubleshooting, and security notes.

### Native development

```bash
cp .env.example .env
uv sync --project apps/api --extra dev
pnpm install
pnpm dev
```

`pnpm dev` starts the API on port 8000 and web client on port 3000. Run `pnpm doctor` before processing media. Model downloads are explicit user actions; see [docs/models.md](docs/models.md).

### Branded local application

Run the supervised local application instead of exposing the development ports directly:

```bash
pnpm local
```

The ReachCut agent starts the API and web processes on private loopback ports, waits for
their health checks, then opens a one-time authorized browser session at
`http://studio.reachcut.localhost:47321`. The public gateway accepts only that hostname,
keeps uploads on one origin, injects a private per-run API token, and stops its child
processes on shutdown. Use `pnpm local:no-browser` on a machine where the URL must be
opened manually. See [docs/local-agent.md](docs/local-agent.md) for the architecture,
security model, packaging contract, configuration, and OS startup integration.

Build a native customer installer on the target operating system with:

```bash
pnpm install --frozen-lockfile
pnpm build:installer -- --version 0.1.0
```

Artifacts are written to `build/installers/`. The release workflow builds Windows x64,
macOS Apple Silicon, macOS Intel, and Linux x64 variants on matching hosted runners. See
[docs/installers.md](docs/installers.md) for bundled components, startup behavior, signing,
and release gates. The Milestone 0 installer intentionally stays application-only: first
run detects Ollama, links to its official installer when missing, downloads the configured
Qwen model only after confirmation, and explains Whisper's first-analysis download. Open
`http://studio.reachcut.localhost:47321/setup` later to rerun those checks.

ReachCut retains the existing `CLIPPER_*` environment-variable prefix, `clipper`
Python import package, database filename, and Docker data-volume name for backward
compatibility. The product rename does not require a configuration or data migration.

```bash
pnpm check
pnpm test
```

The data directory contains the SQLite database, private source media, stage artifacts, and exports. Back it up to preserve completed work.

## Social publishing setup

ReachCut supports one-click account authorization for YouTube, TikTok, Instagram,
Facebook, and X. The person using ReachCut never pastes a user access token, refresh
token, Page ID, or Instagram account ID. The workspace owner must still register a
developer app with each provider once and place that app's client credentials in the
private `.env` file.

If a platform says **Setup required** under **Settings → Connected accounts**, its
required environment variables are empty. ReachCut only reports that a provider is
ready when its client ID/key, client secret, and redirect URI are present.

### Callback URLs and environment variables

For the default local setup, the web application is at `http://127.0.0.1:3000` and
the API is at `http://127.0.0.1:8000`. OAuth callbacks go to the API, not the web
application.

| Platform  | Registered callback                                      | Required `.env` values                                                                       |
| --------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| YouTube   | `http://127.0.0.1:8000/api/oauth/youtube/callback`       | `CLIPPER_YOUTUBE_CLIENT_ID`, `CLIPPER_YOUTUBE_CLIENT_SECRET`, `CLIPPER_YOUTUBE_REDIRECT_URI` |
| TikTok    | `https://YOUR-PUBLIC-API-HOST/api/oauth/tiktok/callback` | `CLIPPER_TIKTOK_CLIENT_KEY`, `CLIPPER_TIKTOK_CLIENT_SECRET`, `CLIPPER_TIKTOK_REDIRECT_URI`   |
| Instagram | `http://127.0.0.1:8000/api/oauth/meta/callback`          | `CLIPPER_META_APP_ID`, `CLIPPER_META_APP_SECRET`, `CLIPPER_META_REDIRECT_URI`                |
| Facebook  | Same Meta callback as Instagram                          | Same Meta variables as Instagram                                                             |
| X         | `http://127.0.0.1:8000/api/oauth/x/callback`             | `CLIPPER_X_CLIENT_ID`, `CLIPPER_X_CLIENT_SECRET`, `CLIPPER_X_REDIRECT_URI`                   |

TikTok Login Kit for web requires an absolute, static HTTPS redirect URI. For local
development, expose port 8000 through an HTTPS reverse proxy or temporary tunnel and
register the resulting callback URL. The tunnel must forward the full
`/api/oauth/tiktok/callback` path to the ReachCut API. Use HTTPS callbacks for every
provider in a deployed environment.

Set `CLIPPER_WEB_BASE_URL` to the URL users open in their browser. ReachCut redirects
back to `${CLIPPER_WEB_BASE_URL}/settings/accounts` after authorization. A deployed
configuration therefore resembles:

```dotenv
CLIPPER_WEB_BASE_URL=https://reachcut.example.com

CLIPPER_YOUTUBE_CLIENT_ID=
CLIPPER_YOUTUBE_CLIENT_SECRET=
CLIPPER_YOUTUBE_REDIRECT_URI=https://api.reachcut.example.com/api/oauth/youtube/callback

CLIPPER_TIKTOK_CLIENT_KEY=
CLIPPER_TIKTOK_CLIENT_SECRET=
CLIPPER_TIKTOK_REDIRECT_URI=https://api.reachcut.example.com/api/oauth/tiktok/callback

CLIPPER_META_APP_ID=
CLIPPER_META_APP_SECRET=
CLIPPER_META_REDIRECT_URI=https://api.reachcut.example.com/api/oauth/meta/callback

CLIPPER_X_CLIENT_ID=
CLIPPER_X_CLIENT_SECRET=
CLIPPER_X_REDIRECT_URI=https://api.reachcut.example.com/api/oauth/x/callback
```

Redirect URIs must match the provider dashboard exactly, including the scheme, host,
port, path, and trailing slash. Do not commit `.env` or put provider secrets in
`.env.example`, frontend variables, screenshots, issue reports, or logs.

### YouTube Shorts

Official references: [YouTube Data API setup](https://developers.google.com/youtube/v3/getting-started),
[OAuth credentials](https://developers.google.com/youtube/registering_an_application),
and [web-server OAuth](https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps).

1. Open Google Cloud Console, create or select a project, and enable **YouTube Data
   API v3** in **APIs & Services → Library**.
2. Configure the Google Auth Platform branding/consent screen. For a private test,
   keep the app in **Testing** and add every Google account that will connect as a
   test user. For an organization-only deployment, use **Internal** if your Google
   Workspace configuration permits it.
3. In **Google Auth Platform → Clients**, create an OAuth client with application
   type **Web application**.
4. Add the exact authorized redirect URI:
   `http://127.0.0.1:8000/api/oauth/youtube/callback`. Google permits loopback HTTP
   callbacks for local development. Use your HTTPS API URL in production.
5. Copy the client ID and client secret into:

   ```dotenv
   CLIPPER_YOUTUBE_CLIENT_ID=your-google-client-id
   CLIPPER_YOUTUBE_CLIENT_SECRET=your-google-client-secret
   CLIPPER_YOUTUBE_REDIRECT_URI=http://127.0.0.1:8000/api/oauth/youtube/callback
   ```

6. ReachCut requests `youtube.upload` to publish videos and `youtube.readonly` to
   synchronize views, likes, and comments. Declare both scopes in the Google Auth
   Platform data-access configuration when required.
7. Restart ReachCut, open **Settings → Connected accounts**, select **YouTube**, and
   approve the consent screen. If an older connection was created before metrics
   support, select **Reconnect** once to grant the read-only scope.

Testing users can connect without completing public verification, subject to Google's
testing restrictions and refresh-token lifetime. A public external app may require
brand and sensitive-scope verification before arbitrary Google accounts can connect.

### TikTok

Official references: [create a TikTok app](https://developers.tiktok.com/doc/getting-started-create-an-app),
[Login Kit for web](https://developers.tiktok.com/docs/en/login-kit-web), and
[Content Posting API Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-get-started).

1. Create an app in TikTok for Developers. Complete its basic information, website,
   terms-of-service URL, privacy-policy URL, and any URL ownership checks requested
   by the portal.
2. Add the **Login Kit** and **Content Posting API** products.
3. Enable **Direct Post** in the Content Posting API configuration.
4. Register an HTTPS Login Kit redirect URI such as
   `https://YOUR-PUBLIC-API-HOST/api/oauth/tiktok/callback`. Plain HTTP loopback URLs
   are not accepted for TikTok's web flow.
5. Request/enable the scopes used by ReachCut: `user.info.basic`, `video.publish`, and
   `video.upload`. The TikTok account owner must grant the publishing scope during
   connection.
6. Copy the app's **Client key** and **Client secret** into:

   ```dotenv
   CLIPPER_TIKTOK_CLIENT_KEY=your-tiktok-client-key
   CLIPPER_TIKTOK_CLIENT_SECRET=your-tiktok-client-secret
   CLIPPER_TIKTOK_REDIRECT_URI=https://YOUR-PUBLIC-API-HOST/api/oauth/tiktok/callback
   ```

7. Restart ReachCut, select **TikTok** under connected accounts, and authorize the
   account. ReachCut stores the returned access/refresh tokens and Open ID in its
   encrypted credential store.

TikTok apps must be reviewed for the requested products and scopes. Direct posts from
an unaudited client are restricted to private visibility. Complete TikTok's Content
Posting API audit before expecting public posts from production accounts.

### Instagram Reels

Official references: [Instagram API with Facebook Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/get-started)
and Meta's [Instagram Reels publishing sample](https://github.com/fbsamples/reels_publishing_apis/tree/main/insta_reels_publishing_api_sample).

1. The destination Instagram account must be a **professional Business account** and
   must be connected to a Facebook Page. The Facebook user authorizing ReachCut must
   have sufficient Page access to create content.
2. Create an app in Meta for Developers using a business-oriented use case that
   provides Facebook Login and the Instagram Graph API.
3. Add/configure **Facebook Login** and register this exact valid OAuth redirect URI:
   `http://127.0.0.1:8000/api/oauth/meta/callback`. Use the public HTTPS API URL for
   production. Instagram and Facebook connections intentionally share this callback.
4. Enable/request the permissions used by ReachCut:
   `instagram_basic`, `instagram_content_publish`, `pages_show_list`, and
   `pages_read_engagement`.
5. Add the Facebook account as an app administrator, developer, or tester while the
   Meta app is in Development mode. For accounts without an app role, switch the app
   Live only after obtaining the required Advanced Access/App Review approvals and
   completing any requested business verification.
6. Copy the Meta App ID and App Secret into:

   ```dotenv
   CLIPPER_META_APP_ID=your-meta-app-id
   CLIPPER_META_APP_SECRET=your-meta-app-secret
   CLIPPER_META_REDIRECT_URI=http://127.0.0.1:8000/api/oauth/meta/callback
   CLIPPER_META_GRAPH_VERSION=v24.0
   ```

7. Restart ReachCut, select **Instagram**, and authorize with the Facebook account
   that manages the linked Page. ReachCut obtains the Page token and linked Instagram
   professional-account ID automatically; neither is entered in the UI.

If the login succeeds but no Instagram destination is found, verify the account is a
professional Business account, the Page is linked, and the authorizing Facebook user
can manage that Page. The current connection flow selects the first eligible linked
Instagram account returned by Meta.

### Facebook Reels

Official reference: Meta's [Facebook Reels publishing sample](https://github.com/fbsamples/reels_publishing_apis/tree/main/fb_reels_publishing_api_sample).

1. Reuse the Meta app and callback configured for Instagram, or create a dedicated
   Meta app if you need separate review and release lifecycles.
2. The authorizing Facebook user must have sufficient access to the destination Page.
   Personal profiles are not publishing destinations for this adapter.
3. Enable/request `pages_show_list`, `pages_read_engagement`, and
   `pages_manage_posts`. Complete App Review/Advanced Access and business verification
   when publishing for users who do not hold a role on the Meta app.
4. Set the same `CLIPPER_META_APP_ID`, `CLIPPER_META_APP_SECRET`, and
   `CLIPPER_META_REDIRECT_URI` values shown in the Instagram section.
5. Restart ReachCut, select **Facebook**, and authorize the Facebook account that
   manages the Page. ReachCut resolves and encrypts the Page access token and Page ID.

The current connection flow selects the first eligible Page returned by Meta. Use a
Facebook login that only manages the intended Page if deterministic selection matters.

### X

Official reference: [OAuth 2.0 Authorization Code Flow with PKCE](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code).

1. Create or select a Project and App in the X Developer Console. Ensure the selected
   X API access tier includes posting and media-upload endpoints.
2. Open the app's **User authentication settings**, enable **OAuth 2.0**, and choose a
   confidential **Web App** client so the app has a Client ID and Client Secret.
3. Register the exact callback URL
   `http://127.0.0.1:8000/api/oauth/x/callback`, plus the required website URL. Use an
   HTTPS callback for a deployed ReachCut instance.
4. Enable the read/write permissions corresponding to the scopes ReachCut requests:
   `tweet.read`, `tweet.write`, `users.read`, `media.write`, and `offline.access`.
   `offline.access` is required for X to issue a refresh token.
5. Copy the OAuth 2.0 Client ID and Client Secret—not the app-only bearer token—into:

   ```dotenv
   CLIPPER_X_CLIENT_ID=your-x-oauth2-client-id
   CLIPPER_X_CLIENT_SECRET=your-x-oauth2-client-secret
   CLIPPER_X_REDIRECT_URI=http://127.0.0.1:8000/api/oauth/x/callback
   ```

6. Restart ReachCut, select **X**, and authorize the account. ReachCut uses OAuth 2.0
   Authorization Code with PKCE and stores the refresh token for future publishing.

### Restart and verify

After changing `.env`, restart the API so provider clients are rebuilt with the new
configuration:

```bash
# Docker Compose
docker compose up -d --build api

# Native development: stop pnpm dev, then start it again
pnpm dev
```

Check what ReachCut detected without displaying any secrets:

```bash
curl -s http://127.0.0.1:8000/api/publishing/capabilities
```

The `configured_platforms` array should contain every configured provider. Instagram
and Facebook appear together because they share the same Meta app credentials. This
endpoint only checks that configuration values exist; the provider validates the
redirect URI, scopes, review status, and account eligibility during authorization.

Finally, open **Settings → Connected accounts**, select a platform, approve access on
the provider's site, then return to ReachCut. Approve and render a clip before using
**Publish with ReachCut**.

Provider access and refresh tokens are encrypted under the private data directory and
are not stored in SQLite. Keep both `credentials.key` and the `credentials/` directory
together when backing up or restoring. TikTok returns an asynchronous publishing ID,
so ReachCut records the upload as processing and provides a status refresh action until
the final post URL is available.

For an end-to-end, function-by-function walkthrough, start with [docs/code-flow.md](docs/code-flow.md). Architectural boundaries and change ownership are documented in [docs/architecture.md](docs/architecture.md) and [docs/module-ownership.md](docs/module-ownership.md). See also [docs/security.md](docs/security.md) and [docs/troubleshooting.md](docs/troubleshooting.md).

## Scope

This repository focuses on the local clipping workflow. Public social-account profiles and publishing defaults can be configured once without storing passwords. Approved, rendered clips can be uploaded through official YouTube, TikTok, Instagram, Facebook, and X APIs, linked to their resulting post URLs, and tracked with timestamped performance and revenue snapshots. YouTube views, likes, and comments synchronize when a project opens and every minute while it remains open; manual snapshot fields preserve revenue, conversions, and other business metrics. Automatic analytics for the other social platforms, Remotion templates, face tracking, and VLM reranking are not yet claimed as complete.

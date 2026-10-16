# ReachCut

ReachCut is a local-first application for turning media you are authorized to repurpose into reviewable vertical clips. The core pipeline uses local models and local FFmpeg processes. Official API adapters can upload approved clips to YouTube, TikTok, Instagram Reels, Facebook Reels, and X without opening each platform's upload interface.

The current vertical slice provides secure local upload and allowlisted URL import through `yt-dlp`, media probing, durable stage state, provider-based `faster-whisper` transcription, configurable Ollama editorial selection, and schema-validated views- and revenue-oriented editing plans. Transcript signals suggest useful clip directions such as funny moments, advice, stories, insights, and educational sections. The Creative Studio adds auto-curated source slices, content modes, OpenCV face/action tracking, caption presets and translation, hook/CTA/card overlays, transitions, zoom/progress effects, gameplay split-screen, B-roll, reaction PIP, SFX, music, and alternate source-audio selection. Deterministic FFmpeg rendering produces review previews and final 9:16 exports. Clips require human approval unless the user explicitly creates an automation pipeline that opts into approval, rendering, and publishing.

For Urdu and other non-English media, select the spoken language when importing the source or before manually requesting analysis. The default `large-v3-turbo` Whisper model substantially improves multilingual recognition, while ASS/libass captions preserve Unicode/RTL shaping. Caption position, font, size, colors, highlighted words, line length, and pop/karaoke animation can be reviewed and changed on each generated clip.

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

Use **Settings** in the ReachCut sidebar to change the Ollama URL and select any
installed model. Use **Automations** to schedule one-time, daily, or weekly
end-to-end flows that analyze a project, select either the best-scored clip or all
matching clips, render them, and publish them to selected connected accounts.

The Automation source step supports existing projects, public video URLs, and local
uploads. URL submission creates a project immediately; downloads and analysis run
in a durable FIFO queue. Uploads join the same queue once the file has been saved.
Manual analysis also uses this queue, with one project processed at a time. View
live stages, cancel work, or retry failed jobs from **Automations** or **Projects**.
Retry preserves the original language and clip settings. Interrupted jobs resume
on API startup using saved stage artifacts. The queue table is created automatically
in the existing database; no additional queue service is required. Keep the API
running for processing and scheduled publishing to continue.


Use **Publishing** in the sidebar to approve selected or all generated clips, render
approved selections, and publish finished exports to accounts, platforms, or social
account groups. Create groups such as Religious, Art, and Tech under **Accounts**;
rename them, change their members, or delete them without disconnecting accounts or
removing published history. An account may belong to several groups. Bulk publishing
shows its exact destinations and skips unapproved clips, missing exports, disconnected
accounts, and posts already queued or published to the same account. Failed attempts
can be retried; concurrent duplicate requests cannot reserve the same clip/account.

**Insights** provides cumulative views charts, group/platform/account filters,
engagement, saved business metrics, and post performance. Totals use only the latest
snapshot per post; currencies remain separate. Automatic refresh skips unavailable
accounts and isolates each provider failure, while saved metrics remain visible.
Expired or revoked credentials require reconnecting the original account in Accounts.
Metrics unavailable through the current provider adapters can still be entered on a
clip's publishing page. Chart period controls the chart; summary cards show latest
lifetime totals for the selected destinations.

For Facebook and Instagram logins with multiple destinations, ReachCut lists the
Pages or linked Instagram accounts after authorization. Choose the destination to
add. Reconnect refreshes only the existing provider account ID and refuses to
replace it with another Page/profile. When granting access to additional Pages in
Meta's login dialog, retain access to your existing destinations too. Each Instagram
professional account must be linked to its corresponding Facebook Page. Account
selection credentials remain encrypted on the API and expire after ten minutes.

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

The connection flow is provider-first: choosing a configured platform starts OAuth
without creating an empty database record. After the provider callback, ReachCut
fetches the authorized channel/profile identity, creates or reconnects that real
account, and stores its tokens in the encrypted credential store. Reauthorizing the
same provider account updates the existing connection instead of adding a duplicate.
This follows the useful separation used by BrightBean Studio—developer-app
configuration is an administrator concern, while connecting a publishing identity is
a short end-user OAuth action—without importing its Django implementation.

If a platform says **Setup required** under **Settings → Connected accounts**, its
required environment variables are empty. Select that platform to open an in-app
from-scratch guide with the current callback URI, required scopes, `.env` variable
names, and a link to the provider's developer portal. ReachCut only reports that a
provider is ready when its client ID/key, client secret, and redirect URI are present.

### Callback URLs and environment variables

For the default local setup, the web application is at `http://127.0.0.1:3000` and
the API is at `http://127.0.0.1:8000`. OAuth callbacks go to the API, not the web
application.

| Platform  | Registered callback                                      | Required `.env` values                                                                       |
| --------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| YouTube   | `http://127.0.0.1:8000/api/oauth/youtube/callback`       | `CLIPPER_YOUTUBE_CLIENT_ID`, `CLIPPER_YOUTUBE_CLIENT_SECRET`, `CLIPPER_YOUTUBE_REDIRECT_URI` |
| TikTok    | `http://127.0.0.1:8000/api/oauth/tiktok/callback`        | `CLIPPER_TIKTOK_CLIENT_KEY`, `CLIPPER_TIKTOK_CLIENT_SECRET`, `CLIPPER_TIKTOK_REDIRECT_URI`   |
| Instagram | `http://localhost:8000/api/oauth/instagram/callback`       | `CLIPPER_INSTAGRAM_APP_ID`, `CLIPPER_INSTAGRAM_APP_SECRET`, `CLIPPER_INSTAGRAM_LOGIN_CONFIG_ID`, `CLIPPER_INSTAGRAM_REDIRECT_URI` |
| Facebook  | `http://localhost:8000/api/oauth/facebook/callback`      | `CLIPPER_FACEBOOK_APP_ID`, `CLIPPER_FACEBOOK_APP_SECRET`, `CLIPPER_FACEBOOK_LOGIN_CONFIG_ID`, `CLIPPER_FACEBOOK_REDIRECT_URI`   |
| X         | `http://127.0.0.1:8000/api/oauth/x/callback`             | `CLIPPER_X_CLIENT_ID`, `CLIPPER_X_CLIENT_SECRET`, `CLIPPER_X_REDIRECT_URI`                   |

Instagram and Facebook both use Meta/Facebook Login with Page permissions, but may
use separate Meta apps and therefore keep separate credentials. Instagram resolves
the professional account linked to the selected Facebook Page and uploads the local
video bytes directly to Meta; it does not expose the rendered clip on a public URL.
Facebook Login can use the literal `localhost` callback while the app remains in
Development mode.

TikTok uses its Desktop Login Kit flow with PKCE, which permits a localhost or
loopback HTTP callback with a port. Publishing then uses `FILE_UPLOAD`, so neither
authorization nor media delivery requires a public ReachCut endpoint.

Every publishing adapter sends media through an outbound upload from the local API:

| Platform  | Local media transport                                      |
| --------- | ---------------------------------------------------------- |
| YouTube   | Google resumable upload session                            |
| TikTok    | Content Posting API `FILE_UPLOAD` chunks                    |
| Instagram | Meta resumable container followed by `rupload.facebook.com` |
| Facebook  | Facebook Reels binary upload session                       |
| X         | X Media API initialize/append/finalize chunks               |

No provider receives a localhost media URL or needs to make an inbound request to
ReachCut.

Set `CLIPPER_WEB_BASE_URL` to the local URL users open in their browser. ReachCut
redirects back to `${CLIPPER_WEB_BASE_URL}/settings/accounts` after authorization.
The complete local-only callback configuration is:

```dotenv
CLIPPER_WEB_BASE_URL=http://127.0.0.1:3000

CLIPPER_YOUTUBE_CLIENT_ID=
CLIPPER_YOUTUBE_CLIENT_SECRET=
CLIPPER_YOUTUBE_REDIRECT_URI=http://127.0.0.1:8000/api/oauth/youtube/callback

CLIPPER_TIKTOK_CLIENT_KEY=
CLIPPER_TIKTOK_CLIENT_SECRET=
CLIPPER_TIKTOK_REDIRECT_URI=http://127.0.0.1:8000/api/oauth/tiktok/callback

CLIPPER_INSTAGRAM_APP_ID=
CLIPPER_INSTAGRAM_APP_SECRET=
CLIPPER_INSTAGRAM_LOGIN_CONFIG_ID=
CLIPPER_INSTAGRAM_REDIRECT_URI=http://localhost:8000/api/oauth/instagram/callback

CLIPPER_FACEBOOK_APP_ID=
CLIPPER_FACEBOOK_APP_SECRET=
CLIPPER_FACEBOOK_LOGIN_CONFIG_ID=
CLIPPER_FACEBOOK_REDIRECT_URI=http://localhost:8000/api/oauth/facebook/callback

CLIPPER_X_CLIENT_ID=
CLIPPER_X_CLIENT_SECRET=
CLIPPER_X_REDIRECT_URI=http://127.0.0.1:8000/api/oauth/x/callback

CLIPPER_GRAPH_API_VERSION=v26.0
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
[Desktop Login Kit](https://developers.tiktok.com/docs/en/login-kit-desktop), and
[Content Posting API Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-get-started).

1. Create an app in TikTok for Developers and configure it as a desktop application.
2. Add **Desktop Login Kit** and the **Content Posting API** products.
3. Enable **Direct Post** in the Content Posting API configuration.
4. Register this exact Desktop Login Kit redirect URI:
   `http://127.0.0.1:8000/api/oauth/tiktok/callback`. ReachCut supplies the required
   PKCE challenge and verifier automatically.
5. Request/enable the scopes used by ReachCut: `user.info.basic`, `video.publish`, and
   `video.upload`. The TikTok account owner must grant the publishing scope during
   connection.
6. Copy the app's **Client key** and **Client secret** into:

   ```dotenv
   CLIPPER_TIKTOK_CLIENT_KEY=your-tiktok-client-key
   CLIPPER_TIKTOK_CLIENT_SECRET=your-tiktok-client-secret
   CLIPPER_TIKTOK_REDIRECT_URI=http://127.0.0.1:8000/api/oauth/tiktok/callback
   ```

7. Restart ReachCut, select **TikTok** under connected accounts, and authorize the
   account. ReachCut stores the returned access/refresh tokens and Open ID in its
   encrypted credential store.

TikTok apps must be reviewed for the requested products and scopes. Direct posts from
an unaudited client are restricted to private visibility. Complete TikTok's Content
Posting API audit before expecting public posts from production accounts.

### Instagram Reels

Official references: Meta's [Instagram Reels publishing sample](https://github.com/fbsamples/reels_publishing_apis/tree/main/insta_reels_publishing_api_sample)
and [Instagram content publishing documentation](https://developers.facebook.com/docs/instagram-api/guides/content-publishing/).

1. The destination Instagram account must be a **professional account** (Business or
   Creator) linked to a Facebook Page. The Facebook user who connects ReachCut must
   have sufficient access to that Page.
2. Sign in at [Meta for Developers](https://developers.facebook.com/apps/), select
   **My Apps → Create App**, create a Business app, and add **Facebook Login for
   Business** plus the Instagram API/content publishing use case.
3. Open **Facebook Login for Business → Configurations**, create a configuration
   using a **User access token**, include the Page/Instagram assets and the permissions
   `pages_show_list`, `pages_read_engagement`, `business_management`,
   `instagram_basic`, and `instagram_content_publish`, then copy its
   **Configuration ID**. `business_management` is needed when Meta holds the Page
   inside a Business Portfolio; without it, `/me/accounts` can return an empty list
   even though the Page permissions are granted.
4. Under Facebook Login settings, add this exact **Valid OAuth Redirect URI**:
   `http://localhost:8000/api/oauth/instagram/callback`.
5. Enable/request `pages_show_list`, `pages_read_engagement`, `business_management`,
   `instagram_basic`, and `instagram_content_publish`.
6. While the app is in Development mode, add the connecting Facebook account as an
   administrator, developer, or tester. Connecting users without an app role requires
   the applicable Advanced Access/App Review approval.
7. Open **App settings → Basic** and copy the Meta app's general **App ID** and
   **App Secret**. Do not use the separate credentials shown under Instagram Login.
   Set:

   ```dotenv
   CLIPPER_INSTAGRAM_APP_ID=your-meta-app-id
   CLIPPER_INSTAGRAM_APP_SECRET=your-meta-app-secret
   CLIPPER_INSTAGRAM_LOGIN_CONFIG_ID=your-facebook-login-configuration-id
   CLIPPER_INSTAGRAM_REDIRECT_URI=http://localhost:8000/api/oauth/instagram/callback
   CLIPPER_GRAPH_API_VERSION=v26.0
   ```

8. Restart ReachCut, select **Reconnect** for the existing Instagram connection (or
   select **Instagram** if none exists), and authorize the Facebook account that
   manages the linked Page.
   ReachCut discovers the linked Instagram account and stores its Page access token.
9. Publishing creates a resumable container on `graph.facebook.com`, uploads the
   rendered file directly to Meta's returned `rupload.facebook.com` URL, waits for
   processing, and publishes it. No tunnel, CDN, or public media URL is used.

### Facebook Reels

Official reference: Meta's [Facebook Reels publishing sample](https://github.com/fbsamples/reels_publishing_apis/tree/main/fb_reels_publishing_api_sample).

1. In [Meta for Developers](https://developers.facebook.com/apps/), select
   **My Apps → Create App** and create a second, dedicated Facebook app. Choose a
   business-oriented use case that supports Facebook Login and managing a Page.
2. The authorizing Facebook user must have sufficient access to the destination Page.
   Personal profiles are not publishing destinations for this adapter.
3. Add/configure **Facebook Login for Business**. Under **Configurations**, create a
   **User access token** configuration containing `pages_show_list`,
   `pages_read_engagement`, `pages_manage_posts`, and `business_management`, then copy
   its Configuration ID.
   In **Settings**, register this exact **Valid OAuth Redirect URI**:
   `http://localhost:8000/api/oauth/facebook/callback`.
4. Enable/request `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, and
   `business_management`. Complete App Review/Advanced Access and business verification
   when publishing for users who do not hold a role on the Meta app.
5. Open **App settings → Basic**, copy this Facebook app's **App ID** and **App
   Secret**, and set:

   ```dotenv
   CLIPPER_FACEBOOK_APP_ID=your-facebook-meta-app-id
   CLIPPER_FACEBOOK_APP_SECRET=your-facebook-meta-app-secret
   CLIPPER_FACEBOOK_LOGIN_CONFIG_ID=your-facebook-login-configuration-id
   CLIPPER_FACEBOOK_REDIRECT_URI=http://localhost:8000/api/oauth/facebook/callback
   ```

6. While the app is in Development mode, add the connecting Facebook account as an
   app administrator, developer, or tester.
7. Restart ReachCut, select **Facebook**, and authorize the Facebook account that
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
and Facebook are checked independently because ReachCut uses separate Meta developer
app credentials for their release and review lifecycles. This endpoint only checks
that configuration values exist; the provider validates the redirect URI, scopes,
review status, and account eligibility during authorization. Its `provider_setup`
array contains only non-secret setup metadata and never exposes client secrets.

Finally, open **Settings → Connected accounts**, select a platform, approve access on
the provider's site, then return to ReachCut. Approve and render a clip before using
**Publish with ReachCut**.

Instagram uploads local files directly, so publishing does not require a public
HTTPS address. If Meta rejects an upload with error 1363008 / `FILE_NOT_FOUND` and
reports zero bytes accepted, ReachCut retries once in a fresh container using a
temporary 720p H.264 Baseline / AAC copy. The original render is preserved. This
compatibility retry happens before publishing; the publish call is never retried
automatically.

Provider access and refresh tokens are encrypted under the private data directory and
are not stored in SQLite. Keep both `credentials.key` and the `credentials/` directory
together when backing up or restoring. TikTok returns an asynchronous publishing ID,
so ReachCut records the upload as processing and provides a status refresh action until
the final post URL is available.

For an end-to-end, function-by-function walkthrough, start with [docs/code-flow.md](docs/code-flow.md). Architectural boundaries and change ownership are documented in [docs/architecture.md](docs/architecture.md) and [docs/module-ownership.md](docs/module-ownership.md). See also [docs/security.md](docs/security.md) and [docs/troubleshooting.md](docs/troubleshooting.md).

## Scope

This repository focuses on the local clipping workflow. Public social-account profiles and publishing defaults can be configured once without storing passwords. Approved, rendered clips can be uploaded through official YouTube, TikTok, Instagram, Facebook, and X APIs, linked to their resulting post URLs, and tracked with timestamped performance and revenue snapshots. YouTube views, likes, and comments synchronize when a project opens and every minute while it remains open; manual snapshot fields preserve revenue, conversions, and other business metrics. Automatic analytics for the other social platforms, Remotion templates, face tracking, and VLM reranking are not yet claimed as complete.

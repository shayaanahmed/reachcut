# ReachCut branded local agent

## Purpose

The local agent turns the existing FastAPI and Next.js processes into one supervised,
browser-delivered desktop application. Customer traffic uses the branded loopback origin:

```text
http://studio.reachcut.localhost:47321
```

The `.localhost` suffix is intentional. Operating systems and browsers reserve it for the
current machine, so it requires no DNS server, hosts-file edit, internet connection, or
locally trusted certificate. The service binds only to `127.0.0.1`; another machine cannot
connect to it.

This feature does not make Python, FFmpeg, Ollama, or model binaries platform-independent.
A commercial installer must still provide the correct signed binaries for Windows x64,
macOS arm64, and each supported Linux architecture.

## Runtime architecture

```text
Browser or installed PWA
        |
        | http://studio.reachcut.localhost:47321
        v
ReachCut agent gateway (127.0.0.1 only)
        |-- /api/*  -> FastAPI, 127.0.0.1:48100
        `-- /*      -> Next.js, 127.0.0.1:48101
                              |
                              |-- Ollama, 127.0.0.1:11434
                              |-- faster-whisper
                              `-- FFmpeg / ffprobe
```

The gateway streams request and response bodies. Large media uploads are not buffered in
the agent or sent through a cloud service.

## Development use

Install the normal development dependencies, start Ollama, and run:

```bash
pnpm local
```

The command starts FastAPI and `next dev`, waits until both answer health requests, starts
the gateway, and opens the default browser. Press `Ctrl+C` in the terminal to stop the
gateway and both supervised processes.

For an environment without a desktop session:

```bash
pnpm local:no-browser
```

The command prints a one-time bootstrap URL. Treat that URL like a short-lived password.
It is valid for two minutes and can be exchanged only once.

To exercise the production Next.js server:

```bash
pnpm --dir apps/web build
pnpm local:production
```

Normal `pnpm dev`, Docker Compose, and their original ports remain available for developer
workflows. They do not enable local-agent authentication unless
`CLIPPER_LOCAL_AGENT_TOKEN` is explicitly set.

## Authentication and request flow

1. The agent generates three independent cryptographically random values on every start:
   an internal API token, a one-time browser bootstrap token, and a browser session token.
2. It passes the internal token to FastAPI through `CLIPPER_LOCAL_AGENT_TOKEN`.
3. FastAPI rejects every request that does not contain the matching internal header.
4. The browser opens a URL with the bootstrap token in the URL fragment. Fragments are not
   included in HTTP requests, proxy logs, or referrer headers.
5. A small gateway-owned page reads the fragment and exchanges it once for an `HttpOnly`,
   `SameSite=Strict` session cookie.
6. The gateway removes browser cookies and any user-supplied internal-token header before
   proxying. It then injects the real internal token only for `/api` requests.
7. `POST`, `PUT`, `PATCH`, and `DELETE` requests must carry the exact branded origin.

The session cookie has a long browser lifetime so the installed PWA can be reopened while
the agent continues running. It becomes useless immediately when the agent restarts,
because the in-memory session token changes.

Additional gateway controls include:

- Exact `Host` validation to reduce DNS-rebinding exposure.
- Loopback-only listeners for the gateway, API, and web server.
- A restrictive Content Security Policy and browser security headers.
- No forwarding of the gateway session cookie to Next.js or FastAPI.
- No shell execution. Every child process receives an executable and argument array.
- Graceful `SIGTERM` followed by a bounded forced stop if a child will not exit.

The internal FastAPI and Next.js ports remain implementation details. Firewalls should not
be configured to expose them, and commercial packages must not change their bind address
from `127.0.0.1`.

## PWA installation

ReachCut now publishes a web-app manifest and application icon. After the agent opens the
site, a supported browser can install it as an application. The precise menu text differs
by browser; in Chromium browsers it is normally **Install ReachCut** in the address bar or
application menu.

The installed application has its own window, launcher icon, and taskbar entry. Its
`start_url` remains the local branded origin and it continues to depend on the ReachCut
agent. The PWA does not install the backend or start models by itself.

## Configuration

The agent reads the repository `.env` file when supported by the installed Node runtime,
then reads these process variables:

| Variable                     | Default                     | Purpose                                                |
| ---------------------------- | --------------------------- | ------------------------------------------------------ |
| `REACHCUT_LOCAL_HOSTNAME`    | `studio.reachcut.localhost` | Public branded hostname; must end in `.localhost`      |
| `REACHCUT_LOCAL_PORT`        | `47321`                     | Public gateway port                                    |
| `REACHCUT_INTERNAL_API_PORT` | `48100`                     | Private FastAPI port                                   |
| `REACHCUT_INTERNAL_WEB_PORT` | `48101`                     | Private Next.js port                                   |
| `REACHCUT_NO_BROWSER`        | unset                       | Set to `1` to print rather than open the bootstrap URL |
| `REACHCUT_API_COMMAND_JSON`  | repository `uv` command     | Packaged API executable and arguments                  |
| `REACHCUT_WEB_COMMAND_JSON`  | repository `pnpm` command   | Packaged web executable and arguments                  |

The three ports must be distinct. The hostname parser accepts only valid DNS labels under
`.localhost`; it deliberately rejects public domains and arbitrary hostnames.

Command overrides are JSON arrays, never shell strings. Installer builds may use the
following placeholders in array elements:

- `{apiPort}`
- `{webPort}`
- `{origin}`
- `{rootDir}`

For example:

```dotenv
REACHCUT_API_COMMAND_JSON=["C:\\Program Files\\ReachCut\\reachcut-api.exe","--port","{apiPort}"]
REACHCUT_WEB_COMMAND_JSON=["C:\\Program Files\\ReachCut\\node.exe","C:\\Program Files\\ReachCut\\web\\server.js"]
```

The agent automatically supplies `CLIPPER_LOCAL_AGENT_TOKEN`, `CLIPPER_WEB_BASE_URL`,
`API_INTERNAL_URL`, `HOSTNAME`, and `PORT` to its children. Installers must not persist the
generated internal or browser tokens.

## OS startup integration

Native installer definitions now live under `packaging/windows`, `packaging/macos`, and
`packaging/linux`. Windows uses a per-user Startup-folder entry, macOS uses a LaunchAgent,
and Linux uses a `systemd --user` unit. These choices keep the agent inside the signed-in
desktop session, where it can open the customer's browser. A Windows Service would run in
session zero and should not attempt to interact with that browser.

The older files under `packaging/local-agent/` remain reference templates. See
`docs/installers.md` for the finalized package behavior and build commands.

## Commercial packaging contract

Development commands still use `uv`, `pnpm`, and source files. `pnpm build:installer`
packages the first five runtime layers below, except that Ollama is still an external
dependency pending the product decision described in `docs/installers.md`:

1. The agent as a signed executable or a pinned Node runtime plus these agent modules.
2. FastAPI as a platform-specific executable or private Python runtime.
3. The Next.js standalone output, including `.next/static` and any public assets.
4. FFmpeg and ffprobe builds with the required codecs and subtitle support.
5. A pinned Ollama runtime or a separately versioned supported Ollama installation.
6. Explicit, checksum-verified model downloads.
7. An updater that stops the agent, backs up mutable data, atomically replaces application
   files, restarts the agent, and rolls back on failed health checks.

Application files, customer data, model caches, logs, and temporary render files must use
separate directories. Uninstall should ask before deleting customer projects and models.

## Social OAuth limitation

The local hostname is appropriate for the ReachCut UI but does not guarantee acceptance as
an OAuth redirect URI. Some publishing platforms require a registered public HTTPS callback.
Those providers need a separate HTTPS callback relay or an explicitly supported loopback
callback. This does not require customer media to leave the machine, but it must be designed
and documented independently of the local gateway.

## Tests

Run the local-agent security and proxy tests alone with:

```bash
pnpm test:agent
```

The root `pnpm test` command includes them. The tests cover hostname restrictions, command
parsing, Host rejection, one-time bootstrap exchange, cookie flags, authenticated proxying,
origin enforcement, security headers, cookie stripping, and internal API-token injection.

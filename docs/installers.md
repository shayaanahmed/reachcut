# ReachCut customer installers

## Supported release artifacts

ReachCut uses one application architecture on every operating system, but a different
native package per target. A package must be built and tested on the operating system and
CPU architecture on which it will run.

| Target                  | Artifact                      | Install scope     | Background startup   |
| ----------------------- | ----------------------------- | ----------------- | -------------------- |
| Windows 11 x64          | Inno Setup `.exe`             | Current user      | Startup-folder entry |
| macOS 13+ Apple Silicon | `.pkg` and `.dmg`             | `/Applications`   | LaunchAgent          |
| macOS 13+ Intel         | `.pkg` and `.dmg`             | `/Applications`   | LaunchAgent          |
| Ubuntu/Debian x64       | `.deb` and portable `.tar.gz` | System for `.deb` | systemd user unit    |

The browser always opens `http://studio.reachcut.localhost:47321`. No package edits the
hosts file, installs a local root certificate, exposes a LAN port, or requires Docker.

## Personal and stable channels

ReachCut has two package profiles built from the same source commit. They can be installed
side by side and never share application state:

| Profile  | Application       | Browser origin                                  | Data directory name   | Distribution                         |
| -------- | ----------------- | ----------------------------------------------- | --------------------- | ------------------------------------ |
| Personal | ReachCut Personal | `http://studio.personal.reachcut.localhost:47331` | `ReachCut Personal` or `reachcut-personal` | Private workflow artifact |
| Stable   | ReachCut          | `http://studio.reachcut.localhost:47321`        | `ReachCut` or `reachcut` | Signed customer release              |

Personal uses separate bundle/package identifiers, startup services, installation roots,
ports, browser cookies, and mutable data. Ollama remains a machine-level service, so its
Qwen weights can be reused by both profiles. A manual workflow run defaults to Personal;
a `personal-v*` tag builds Personal, and a `v*` tag always builds Stable.

## What is bundled

The build creates a platform-specific staging directory before invoking a native package
tool. It contains:

1. The ReachCut gateway and supervisor JavaScript modules.
2. A private Node.js runtime. The customer does not install Node or pnpm.
3. The Next.js standalone production server, static chunks, and public assets.
4. A PyInstaller `onedir` build of the FastAPI application and its Python dependencies.
   The customer does not install Python or uv.
5. Static FFmpeg and ffprobe binaries from the pinned JavaScript dependencies.
6. A package manifest containing executable-and-argument arrays. Commands are never
   evaluated by a shell.

The selected Milestone 0 policy is the **small installer**. The package does not bundle
Ollama or model weights. On first launch, `/setup`:

1. Detects Ollama through its loopback-only HTTP API at `127.0.0.1:11434`.
2. Links to the [official Ollama download](https://ollama.com/download) when the runtime
   is absent. ReachCut never downloads or executes a third-party privileged installer.
3. Lets the customer explicitly download `qwen3:8b-q4_K_M` through Ollama's local pull
   API. Interrupted Ollama pulls can be resumed.
4. Explains that `large-v3-turbo` is downloaded and cached by faster-whisper during the
   first video analysis.

The dashboard opens after Ollama, the configured editorial model, FFmpeg, and ffprobe are
available. The setup page remains accessible from the sidebar for diagnostics. Model
downloads require internet access and can consume several gigabytes. A future offline
edition may bundle reviewed model snapshots, but it is not part of Milestone 0.

## Customer data locations

The installed application directory is treated as read-only. At runtime the packaged
agent overrides the API paths so mutable state is stored here:

| Platform | Data, database, projects, and model cache root                 |
| -------- | -------------------------------------------------------------- |
| Windows  | `%LOCALAPPDATA%\ReachCut`                                      |
| macOS    | `~/Library/Application Support/ReachCut`                       |
| Linux    | `$XDG_DATA_HOME/reachcut`, otherwise `~/.local/share/reachcut` |

The SQLite database is `clipper.db` inside that directory. Hugging Face downloads use its
`cache/huggingface` child. Uninstallers intentionally leave customer projects and model
caches in place; deletion needs a separate explicit user choice.

Managed deployments and package smoke tests may override the root with
`REACHCUT_DATA_DIR`. The installer does not set that variable for normal customers.

## Reproducible local build

Prerequisites:

- Node.js `24.11.1` and pnpm `11.19.0`
- Python `3.13` and uv `0.12.5`
- Inno Setup 6 on Windows
- `pkgbuild` and `hdiutil` on macOS
- `dpkg-deb` and `tar` on Linux

From the repository root:

```bash
pnpm install --frozen-lockfile
pnpm check
pnpm test
pnpm build:installer -- --version 0.1.0
```

Choose the profile explicitly for release work:

```bash
pnpm build:personal -- --version 0.1.0
pnpm build:stable -- --version 0.1.0
```

`packaging/build-release.mjs` performs these steps without shell-based child execution:

1. Builds Next.js in standalone mode.
2. Runs pinned PyInstaller `6.16.0` in the API uv environment.
3. Runs `packaging/build-stage.mjs` to assemble and validate the immutable payload.
4. Invokes the current OS package builder.

Use `pnpm build:stage -- --version 0.1.0` to stop after staging. Build output is always
under `build/`, which is ignored by Git.

## Automated release matrix

`.github/workflows/release-installers.yml` runs manually or for `personal-v*`/`v*` tags.
Manual runs offer a Personal/Stable choice and default to Personal. Tags ignore that input
and select their named channel: `personal-v0.1.0` builds Personal while `v0.1.0` builds Stable.
The Personal tag is especially useful before the workflow has reached the default branch.
The matrix uses native hosted runners for Windows x64, macOS arm64, macOS Intel, and Linux
x64, then uploads each unsigned package as a short-lived workflow artifact. The artifacts
are intentionally labelled unsigned because no ReachCut signing identities exist yet. The
Linux build uses Ubuntu 22.04 to avoid unnecessarily raising the minimum glibc version.

The workflow does not publish a GitHub Release. This prevents an unsigned build from being
presented as a customer-ready binary.

## Platform behavior

### Windows

The Inno Setup package installs per-user under `%LOCALAPPDATA%\Programs\ReachCut`, so it
does not need administrator rights. Its Start Menu and optional desktop shortcuts invoke
`wscript.exe` with a small bundled VBScript launcher, avoiding a console window. The
default startup task creates a current-user Startup-folder shortcut that starts the agent
without opening a browser. Inno Setup owns all shortcuts and removes them on uninstall.

### macOS

The PKG places `ReachCut.app` under `/Applications` and a LaunchAgent under
`/Library/LaunchAgents`. The app is an agent-style bundle (`LSUIElement`) and launches the
browser rather than displaying an embedded web view. The DMG is also generated for normal
drag-to-Applications distribution; that variant starts when the user opens the app but
does not install the system LaunchAgent. Production distribution requires Developer ID
signing and Apple notarization for the app, package, and DMG.

### Linux

The Debian package installs immutable files under `/opt/reachcut`, a `/usr/bin/reachcut`
launcher, a desktop entry, icon, and systemd user unit. Its maintainer script enables the
unit globally so each desktop user starts a private local agent at login. The portable
archive adds a relative launcher to the staged payload but does not register startup
integration.

## Signing and release gates

Current outputs are unsigned development installers suitable for internal clean-machine
testing only. Nothing in the repository pretends that signing is configured. Acquire the
following identities before customer distribution:

- **Windows:** a code-signing certificate issued to the legal publisher by a publicly
  trusted certificate authority, plus its protected hardware or cloud signing key. Use it
  for Authenticode signing and timestamping of the installer and shipped executables.
- **macOS:** an Apple Developer Program organization membership, a `Developer ID
  Application` certificate for the app/executables, a `Developer ID Installer` certificate
  for the PKG, and App Store Connect notarization credentials (API key, issuer ID, key ID,
  and Team ID). Sign with hardened runtime, notarize, and staple the ticket.
- **Linux:** a release GPG key held outside the repository for detached checksums now and
  signed APT repository metadata if a package repository is introduced.

After the identities exist, store them only in protected CI environments, require approval
for release jobs, and enable signing only for protected version tags. Also complete these
release gates:

- Malware scan and clean-machine install, upgrade, repair, and uninstall tests.
- A software bill of materials and license review for Python packages, Node packages,
  FFmpeg codecs, Ollama, and downloaded models.
- Freeze and record the approved Ollama/model versions or digests used for customer QA.
- Automatic update and rollback design. The current packages support fresh installation
  and replacement, but do not implement an updater.

Signing identities are intentionally not hard-coded. They belong in protected CI secrets
and should only be activated on protected version tags.

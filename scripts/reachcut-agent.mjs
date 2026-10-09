#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import {
  createGateway,
  gatewayIsRunning,
  parseCommand,
  parsePort,
  randomToken,
  resolveUserDataDir,
  validateLocalHostname,
  waitForHttp,
} from "./reachcut-agent-lib.mjs";

const rootDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const envFile = path.join(rootDir, ".env");
if (existsSync(envFile) && typeof process.loadEnvFile === "function")
  process.loadEnvFile(envFile);

const packageManifestPath = path.join(rootDir, "reachcut-package.json");
let packageManifest = null;
if (existsSync(packageManifestPath)) {
  packageManifest = JSON.parse(readFileSync(packageManifestPath, "utf8"));
  if (
    packageManifest?.schemaVersion !== 1 ||
    !Array.isArray(packageManifest.apiCommand) ||
    !Array.isArray(packageManifest.webCommand)
  ) {
    throw new Error(
      "reachcut-package.json is not a supported package manifest",
    );
  }
}

const production =
  packageManifest !== null || process.argv.includes("--production");
const noBrowser =
  process.argv.includes("--no-browser") ||
  process.env.REACHCUT_NO_BROWSER === "1";
const publicHostname = validateLocalHostname(
  process.env.REACHCUT_LOCAL_HOSTNAME ?? "studio.reachcut.localhost",
);
const publicPort = parsePort(
  process.env.REACHCUT_LOCAL_PORT ?? "47321",
  "REACHCUT_LOCAL_PORT",
);
const apiPort = parsePort(
  process.env.REACHCUT_INTERNAL_API_PORT ?? "48100",
  "REACHCUT_INTERNAL_API_PORT",
);
const webPort = parsePort(
  process.env.REACHCUT_INTERNAL_WEB_PORT ?? "48101",
  "REACHCUT_INTERNAL_WEB_PORT",
);
if (new Set([publicPort, apiPort, webPort]).size !== 3) {
  throw new Error("ReachCut public, API, and web ports must be different");
}

const publicOrigin = `http://${publicHostname}${publicPort === 80 ? "" : `:${publicPort}`}`;
const apiToken = randomToken();
const bootstrapToken = randomToken();
const sessionToken = randomToken();
const replacements = { apiPort, webPort, origin: publicOrigin, rootDir };
const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";

const apiCommand = parseCommand(
  process.env.REACHCUT_API_COMMAND_JSON,
  "REACHCUT_API_COMMAND_JSON",
  replacements,
) ??
  (packageManifest
    ? parseCommand(
        JSON.stringify(packageManifest.apiCommand),
        "packaged API command",
        replacements,
      )
    : null) ?? [
    "uv",
    "run",
    "--project",
    "apps/api",
    "uvicorn",
    "clipper.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    String(apiPort),
  ];
const webCommand = parseCommand(
  process.env.REACHCUT_WEB_COMMAND_JSON,
  "REACHCUT_WEB_COMMAND_JSON",
  replacements,
) ??
  (packageManifest
    ? parseCommand(
        JSON.stringify(packageManifest.webCommand),
        "packaged web command",
        replacements,
      )
    : null) ?? [
    pnpm,
    "--dir",
    "apps/web",
    "exec",
    "next",
    production ? "start" : "dev",
    "--hostname",
    "127.0.0.1",
    "--port",
    String(webPort),
  ];

if (
  production &&
  packageManifest === null &&
  !existsSync(path.join(rootDir, "apps/web/.next/BUILD_ID"))
) {
  throw new Error(
    "Production web build is missing. Run `pnpm --dir apps/web build` first.",
  );
}

const children = new Set();
let stopping = false;

const packagedEnvironment = {};
if (packageManifest) {
  const dataDir = process.env.REACHCUT_DATA_DIR
    ? path.resolve(process.env.REACHCUT_DATA_DIR)
    : resolveUserDataDir(process.platform, process.env, os.homedir());
  const cacheDir = path.join(dataDir, "cache");
  const binariesDir = path.join(rootDir, "bin");
  mkdirSync(dataDir, { recursive: true });
  mkdirSync(cacheDir, { recursive: true });
  packagedEnvironment.CLIPPER_DATA_DIR = dataDir;
  packagedEnvironment.CLIPPER_DATABASE_URL = `sqlite:///${path
    .join(dataDir, "clipper.db")
    .replaceAll("\\", "/")}`;
  packagedEnvironment.HF_HOME = path.join(cacheDir, "huggingface");
  packagedEnvironment.PATH = `${binariesDir}${path.delimiter}${process.env.PATH ?? ""}`;
}

function startChild(name, command, extraEnv = {}) {
  const [executable, ...args] = command;
  const child = spawn(executable, args, {
    cwd: rootDir,
    env: { ...process.env, ...packagedEnvironment, ...extraEnv },
    shell: false,
    stdio: "inherit",
    windowsHide: true,
  });
  children.add(child);
  child.once("error", (error) => {
    console.error(`${name} could not start: ${error.message}`);
    if (!stopping) void shutdown(1);
  });
  child.once("exit", (code, signal) => {
    children.delete(child);
    if (!stopping) {
      console.error(
        `${name} stopped unexpectedly (${signal ?? `exit ${code}`}).`,
      );
      void shutdown(1);
    }
  });
  return child;
}

async function stopChild(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((resolve) => child.once("exit", resolve));
  if (process.platform === "win32" && child.pid) {
    spawn("taskkill.exe", ["/PID", String(child.pid), "/T"], {
      shell: false,
      stdio: "ignore",
      windowsHide: true,
    });
  } else {
    child.kill("SIGTERM");
  }
  const timeout = new Promise((resolve) =>
    setTimeout(resolve, 10_000, "timeout"),
  );
  if (
    (await Promise.race([exited, timeout])) === "timeout" &&
    child.exitCode === null
  ) {
    if (process.platform === "win32" && child.pid) {
      spawn("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
        shell: false,
        stdio: "ignore",
        windowsHide: true,
      });
    } else {
      child.kill("SIGKILL");
    }
  }
}

function openBrowser(url) {
  const command =
    process.platform === "darwin"
      ? ["open", url]
      : process.platform === "win32"
        ? ["rundll32.exe", "url.dll,FileProtocolHandler", url]
        : ["xdg-open", url];
  const [executable, ...args] = command;
  const opener = spawn(executable, args, {
    detached: true,
    shell: false,
    stdio: "ignore",
    windowsHide: true,
  });
  opener.once("error", (error) => {
    console.warn(`Could not open the browser automatically: ${error.message}`);
    console.warn(`Open this one-time URL manually: ${url}`);
  });
  opener.unref();
}

if (await gatewayIsRunning(publicHostname, publicPort)) {
  console.log(`ReachCut is already running at ${publicOrigin}`);
  if (!noBrowser) openBrowser(publicOrigin);
  process.exit(0);
}

const gateway = createGateway({
  publicHostname,
  publicPort,
  apiPort,
  webPort,
  apiToken,
  bootstrapToken,
  sessionToken,
  development: !production,
});

async function closeGateway() {
  if (!gateway.server.listening) return;
  await new Promise((resolve) => gateway.server.close(resolve));
}

async function shutdown(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  console.log("Stopping ReachCut local services…");
  await closeGateway();
  await Promise.all([...children].map(stopChild));
  process.exitCode = exitCode;
}

process.once("SIGINT", () => void shutdown());
process.once("SIGTERM", () => void shutdown());

startChild("ReachCut API", apiCommand, {
  CLIPPER_LOCAL_AGENT_TOKEN: apiToken,
  CLIPPER_WEB_BASE_URL: publicOrigin,
  CLIPPER_WEB_PORT: String(publicPort),
});
startChild("ReachCut web", webCommand, {
  API_INTERNAL_URL: `http://127.0.0.1:${apiPort}`,
  HOSTNAME: "127.0.0.1",
  PORT: String(webPort),
});

try {
  await Promise.all([
    waitForHttp(`http://127.0.0.1:${apiPort}/api/health`, {
      headers: { "X-ReachCut-Agent-Token": apiToken },
    }),
    waitForHttp(`http://127.0.0.1:${webPort}/`),
  ]);
  await new Promise((resolve, reject) => {
    gateway.server.once("error", reject);
    gateway.server.listen(publicPort, "127.0.0.1", resolve);
  });
  const launchUrl = gateway.bootstrapUrl();
  console.log(`ReachCut is ready at ${publicOrigin}`);
  if (noBrowser) console.log(`One-time browser URL: ${launchUrl}`);
  else openBrowser(launchUrl);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  await shutdown(1);
}

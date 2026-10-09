#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import process from "node:process";

function option(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? null : process.argv[index + 1];
}

function redact(output) {
  return output.replaceAll(/(#token=)[^\s]+/g, "$1[redacted]");
}

function gatewayIsRunning(hostname, port, timeoutMs = 1_000) {
  return new Promise((resolve) => {
    const authority = `${hostname}${port === 80 ? "" : `:${port}`}`;
    const request = http.get(
      {
        hostname: "127.0.0.1",
        port,
        path: "/__reachcut/health",
        headers: { Host: authority },
      },
      (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      },
    );
    request.setTimeout(timeoutMs, () => request.destroy());
    request.once("error", () => resolve(false));
  });
}

async function stopProcessTree(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;

  if (process.platform === "win32" && child.pid) {
    spawnSync("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
      shell: false,
      stdio: "ignore",
      windowsHide: true,
    });
    return;
  }

  const exited = new Promise((resolve) => child.once("exit", resolve));
  child.kill("SIGTERM");
  if (
    (await Promise.race([
      exited,
      new Promise((resolve) => setTimeout(resolve, 15_000, "timeout")),
    ])) === "timeout"
  ) {
    child.kill("SIGKILL");
  }
}

const root = path.resolve(option("--root") ?? "");
const manifestPath = path.join(root, "reachcut-package.json");
if (!existsSync(manifestPath)) {
  throw new Error(`Installed package manifest is missing: ${manifestPath}`);
}

const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
if (manifest?.schemaVersion !== 1) {
  throw new Error(`Unsupported installed package manifest: ${manifestPath}`);
}

const executable = path.join(
  root,
  "runtime",
  process.platform === "win32" ? "node.exe" : "node",
);
const agent = path.join(root, "scripts", "reachcut-agent.mjs");
for (const requiredPath of [executable, agent]) {
  if (!existsSync(requiredPath)) {
    throw new Error(`Installed runtime file is missing: ${requiredPath}`);
  }
}

async function requestPrintedLaunch(environment) {
  const launcher = spawn(
    executable,
    [agent, "--production", "--print-browser-url"],
    {
      cwd: root,
      env: { ...environment, REACHCUT_NO_BROWSER: "0" },
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    },
  );
  let launcherOutput = "";
  for (const stream of [launcher.stdout, launcher.stderr]) {
    stream.on("data", (chunk) => {
      launcherOutput = `${launcherOutput}${chunk}`.slice(-20_000);
    });
  }
  return new Promise((resolve, reject) => {
    const launcherTimeout = setTimeout(() => {
      void stopProcessTree(launcher).finally(() =>
        reject(new Error("Timed out testing a second app launch")),
      );
    }, 10_000);
    launcher.once("error", (error) => {
      clearTimeout(launcherTimeout);
      reject(error);
    });
    launcher.once("exit", (code, signal) => {
      clearTimeout(launcherTimeout);
      const url = launcherOutput.match(/One-time browser URL: (\S+)/)?.[1];
      if (code !== 0 || !url) {
        reject(
          new Error(
            `Second app launch did not receive a browser URL (${signal ?? `exit ${code}`}).\n${redact(launcherOutput)}`,
          ),
        );
        return;
      }
      resolve(url);
    });
  });
}

if (await gatewayIsRunning(manifest.localHostname, manifest.localPort)) {
  await requestPrintedLaunch(process.env);
  console.log(
    `Installed background agent and second-launch smoke tests passed for ${manifest.product} ${manifest.version}`,
  );
  process.exit(0);
}

const dataDirectory = await mkdtemp(
  path.join(os.tmpdir(), "reachcut-installed-smoke-"),
);
const runtimeEnvironment = {
  ...process.env,
  REACHCUT_DATA_DIR: dataDirectory,
};
const child = spawn(executable, [agent, "--production", "--no-browser"], {
  cwd: root,
  env: {
    ...runtimeEnvironment,
    REACHCUT_NO_BROWSER: "1",
  },
  shell: false,
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});

let output = "";
const collect = (chunk) => {
  output = `${output}${chunk}`.slice(-100_000);
};
child.stdout.on("data", collect);
child.stderr.on("data", collect);

let timeout;
try {
  await new Promise((resolve, reject) => {
    const ready = () => {
      if (output.includes("One-time browser URL:")) resolve();
    };
    child.stdout.on("data", ready);
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      reject(
        new Error(
          `Installed ReachCut stopped before becoming ready (${signal ?? `exit ${code}`}).\n${redact(output)}`,
        ),
      );
    });
    timeout = setTimeout(
      () =>
        reject(
          new Error(
            `Timed out waiting for installed ReachCut.\n${redact(output)}`,
          ),
        ),
      120_000,
    );
  });
  const initialUrl = output.match(/One-time browser URL: (\S+)/)?.[1];
  if (!initialUrl) throw new Error("Cold start did not print a browser URL");

  const activatedUrl = await requestPrintedLaunch(runtimeEnvironment);
  if (activatedUrl === initialUrl) {
    throw new Error(
      "Second app launch reused the cold-start browser authorization URL",
    );
  }
  console.log(
    `Installed runtime and second-launch smoke tests passed for ${manifest.product} ${manifest.version}`,
  );
} finally {
  clearTimeout(timeout);
  await stopProcessTree(child);
  await rm(dataDirectory, { recursive: true, force: true });
}

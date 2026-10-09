#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, readFile, rm } from "node:fs/promises";
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

  const activation = spawn(
    executable,
    [agent, "--production", "--print-browser-url"],
    {
      cwd: root,
      env: { ...runtimeEnvironment, REACHCUT_NO_BROWSER: "0" },
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    },
  );
  let activationOutput = "";
  for (const stream of [activation.stdout, activation.stderr]) {
    stream.on("data", (chunk) => {
      activationOutput = `${activationOutput}${chunk}`.slice(-20_000);
    });
  }
  const activationExit = await new Promise((resolve, reject) => {
    const activationTimeout = setTimeout(() => {
      activation.kill();
      reject(new Error("Timed out testing a second app launch"));
    }, 10_000);
    activation.once("error", (error) => {
      clearTimeout(activationTimeout);
      reject(error);
    });
    activation.once("exit", (code, signal) => {
      clearTimeout(activationTimeout);
      resolve({ code, signal });
    });
  });
  const activatedUrl = activationOutput.match(
    /One-time browser URL: (\S+)/,
  )?.[1];
  if (
    activationExit.code !== 0 ||
    !activatedUrl ||
    activatedUrl === initialUrl
  ) {
    throw new Error(
      `Second app launch did not receive a fresh browser URL (${activationExit.signal ?? `exit ${activationExit.code}`}).\n${redact(activationOutput)}`,
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

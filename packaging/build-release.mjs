#!/usr/bin/env node

import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { releaseProfile } from "./release-profile.mjs";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

function option(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}

function run(executable, args) {
  console.log(`> ${executable} ${args.join(" ")}`);
  const result = spawnSync(executable, args, {
    cwd: repositoryRoot,
    env: process.env,
    shell: false,
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${executable} failed with exit code ${result.status}`);
  }
}

const version = option("--version", "0.1.0");
if (!/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error("--version must be a semantic version such as 0.1.0");
}
const profile = releaseProfile(option("--channel", "stable"));
process.env.NEXT_PUBLIC_REACHCUT_CHANNEL = profile.channel;

const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const uv = process.platform === "win32" ? "uv.exe" : "uv";
const stageDirectory = path.join(
  repositoryRoot,
  "build",
  profile.channel === "stable" ? "stage" : `stage-${profile.channel}`,
);
const apiDirectory = path.join(
  repositoryRoot,
  "build",
  "pyinstaller",
  "reachcut-api",
);
const outputDirectory = path.join(repositoryRoot, "build", "installers");

run(pnpm, ["--dir", "apps/web", "build"]);
run(uv, [
  "run",
  "--project",
  "apps/api",
  "--with",
  "pyinstaller==6.16.0",
  "pyinstaller",
  "--clean",
  "--noconfirm",
  "--distpath",
  path.join(repositoryRoot, "build", "pyinstaller"),
  "--workpath",
  path.join(repositoryRoot, "build", "pyinstaller-work"),
  path.join(repositoryRoot, "packaging", "runtime", "reachcut-api.spec"),
]);
run(process.execPath, [
  path.join(repositoryRoot, "packaging", "build-stage.mjs"),
  "--api-dir",
  apiDirectory,
  "--output",
  stageDirectory,
  "--version",
  version,
  "--channel",
  profile.channel,
]);

if (process.argv.includes("--stage-only")) process.exit(0);

if (process.platform === "win32") {
  const configuredCompiler = process.env.INNO_SETUP_COMPILER;
  const defaultCompiler = path.join(
    process.env["ProgramFiles(x86)"] ?? "C:\\Program Files (x86)",
    "Inno Setup 6",
    "ISCC.exe",
  );
  const compiler = configuredCompiler ?? defaultCompiler;
  if (!existsSync(compiler)) {
    throw new Error(
      "Inno Setup 6 is required; set INNO_SETUP_COMPILER to ISCC.exe",
    );
  }
  run(compiler, [
    `/DAppVersion=${version}`,
    `/DAppName=${profile.displayName}`,
    `/DAppId=${profile.windowsAppId}`,
    `/DArtifactName=${profile.artifactName}`,
    `/DStageDir=${stageDirectory}`,
    `/DOutputDir=${outputDirectory}`,
    path.join(repositoryRoot, "packaging", "windows", "ReachCut.iss"),
  ]);
} else if (process.platform === "darwin") {
  run("sh", [
    path.join(repositoryRoot, "packaging", "macos", "build-installer.sh"),
    stageDirectory,
    outputDirectory,
    version,
    profile.channel,
  ]);
} else if (process.platform === "linux") {
  run("sh", [
    path.join(repositoryRoot, "packaging", "linux", "build-installer.sh"),
    stageDirectory,
    outputDirectory,
    version,
    profile.channel,
  ]);
} else {
  throw new Error(`Installer builds are not supported on ${process.platform}`);
}

#!/usr/bin/env node

import { createRequire } from "node:module";
import {
  chmodSync,
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import {
  copyDirectoryDereferenced,
  copyDirectoryPreservingLinks,
  validatePortableLinks,
} from "./copy-directory.mjs";
import { profileDataDirectory, releaseProfile } from "./release-profile.mjs";

const require = createRequire(import.meta.url);
const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

function option(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}

function requireDirectory(directory, description) {
  if (!directory || !existsSync(directory)) {
    throw new Error(
      `${description} is missing: ${directory ?? "not provided"}`,
    );
  }
  return path.resolve(directory);
}

async function copyDirectory(source, destination, description) {
  console.log(`Copying ${description}...`);
  if (process.platform !== "win32") {
    await copyDirectoryPreservingLinks(source, destination);
    return;
  }

  // pnpm's standalone output contains directory links that Windows runners
  // cannot follow or recreate. Resolve each link and stage ordinary content.
  await copyDirectoryDereferenced(source, destination);
}

const platform = option("--platform", process.platform);
const architecture = option("--arch", process.arch);
const version = option("--version", "0.1.0");
const profile = releaseProfile(option("--channel", "stable"));
const outputDirectory = path.resolve(
  option("--output", path.join(repositoryRoot, "build", "stage")),
);
const apiDirectory = requireDirectory(
  option("--api-dir"),
  "PyInstaller API directory",
);
const standaloneDirectory = requireDirectory(
  path.join(repositoryRoot, "apps", "web", ".next", "standalone"),
  "Next.js standalone output",
);
const staticDirectory = requireDirectory(
  path.join(repositoryRoot, "apps", "web", ".next", "static"),
  "Next.js static output",
);
const apiExecutable = path.join(
  apiDirectory,
  platform === "win32" ? "reachcut-api.exe" : "reachcut-api",
);
if (!existsSync(apiExecutable)) {
  throw new Error(`Packaged API executable is missing: ${apiExecutable}`);
}

const allowedOutputRoot = path.join(repositoryRoot, "build");
if (
  outputDirectory === allowedOutputRoot ||
  !outputDirectory.startsWith(`${allowedOutputRoot}${path.sep}`)
) {
  throw new Error("--output must be a child of the repository build directory");
}

rmSync(outputDirectory, { recursive: true, force: true });
mkdirSync(outputDirectory, { recursive: true });

await copyDirectory(
  apiDirectory,
  path.join(outputDirectory, "api"),
  "packaged API",
);
await copyDirectory(
  standaloneDirectory,
  path.join(outputDirectory, "web"),
  "standalone web application",
);
await copyDirectory(
  staticDirectory,
  path.join(outputDirectory, "web", "apps", "web", ".next", "static"),
  "web static assets",
);
const publicDirectory = path.join(repositoryRoot, "apps", "web", "public");
if (existsSync(publicDirectory)) {
  await copyDirectory(
    publicDirectory,
    path.join(outputDirectory, "web", "apps", "web", "public"),
    "web public assets",
  );
}

const scriptsDirectory = path.join(outputDirectory, "scripts");
mkdirSync(scriptsDirectory, { recursive: true });
for (const file of ["reachcut-agent.mjs", "reachcut-agent-lib.mjs"]) {
  cpSync(
    path.join(repositoryRoot, "scripts", file),
    path.join(scriptsDirectory, file),
  );
}

const runtimeDirectory = path.join(outputDirectory, "runtime");
mkdirSync(runtimeDirectory, { recursive: true });
const nodeName = platform === "win32" ? "node.exe" : "node";
cpSync(realpathSync(process.execPath), path.join(runtimeDirectory, nodeName));
if (platform !== "win32")
  chmodSync(path.join(runtimeDirectory, nodeName), 0o755);

const binariesDirectory = path.join(outputDirectory, "bin");
mkdirSync(binariesDirectory, { recursive: true });
const ffmpegPath = require("ffmpeg-static");
const ffprobeModule = require("ffprobe-static");
const ffprobePath = ffprobeModule.path ?? ffprobeModule;
for (const [name, source] of [
  [platform === "win32" ? "ffmpeg.exe" : "ffmpeg", ffmpegPath],
  [platform === "win32" ? "ffprobe.exe" : "ffprobe", ffprobePath],
]) {
  cpSync(source, path.join(binariesDirectory, name));
  if (platform !== "win32")
    chmodSync(path.join(binariesDirectory, name), 0o755);
}

const executableSuffix = platform === "win32" ? ".exe" : "";
const separator = platform === "win32" ? "\\" : "/";
const manifest = {
  schemaVersion: 1,
  product: profile.displayName,
  channel: profile.channel,
  version,
  platform,
  architecture,
  localHostname: profile.localHostname,
  localPort: profile.localPort,
  internalApiPort: profile.internalApiPort,
  internalWebPort: profile.internalWebPort,
  dataDirectoryName: profileDataDirectory(profile, platform),
  apiCommand: [
    `{rootDir}${separator}api${separator}reachcut-api${executableSuffix}`,
    "--port",
    "{apiPort}",
  ],
  webCommand: [
    `{rootDir}${separator}runtime${separator}${nodeName}`,
    `{rootDir}${separator}web${separator}apps${separator}web${separator}server.js`,
  ],
};
writeFileSync(
  path.join(outputDirectory, "reachcut-package.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
);

const licensePath = path.join(repositoryRoot, "LICENSE");
if (existsSync(licensePath)) {
  writeFileSync(
    path.join(outputDirectory, "LICENSE"),
    readFileSync(licensePath),
  );
}

await validatePortableLinks(outputDirectory);

console.log(
  `Staged ${profile.displayName} ${version} for ${platform}-${architecture}`,
);
console.log(outputDirectory);

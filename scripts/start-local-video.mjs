import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const engineRoot = join(
  repository,
  "apps",
  "api",
  "data",
  "local-video",
  "LTX-Desktop",
);
const backend = join(engineRoot, "backend");
const python = join(backend, ".venv", "bin", "python");
const dataDir = join(repository, "apps", "api", "data", "local-video", "ltx-data");

if (!existsSync(python)) {
  console.error("Local video engine is not installed. Run pnpm video:setup first.");
  process.exit(1);
}
mkdirSync(dataDir, { recursive: true });
writeFileSync(
  join(dataDir, "reachcut-engine.json"),
  `${JSON.stringify({ data_dir: dataDir, url: "http://127.0.0.1:41954" }, null, 2)}\n`,
  "utf8",
);
const sdk = spawnSync("xcrun", ["--sdk", "macosx", "--show-sdk-path"], {
  encoding: "utf8",
});
const bindHost = process.env.CLIPPER_VIDEO_ENGINE_BIND_HOST ?? "0.0.0.0";
const result = spawnSync(
  python,
  [
    "-m",
    "uvicorn",
    "ltx2_server:app",
    "--host",
    bindHost,
    "--port",
    "41954",
    "--log-level",
    "info",
    "--no-access-log",
  ],
  {
    cwd: backend,
    env: {
      ...process.env,
      LTX_APP_DATA_DIR: dataDir,
      LTX_PORT: "41954",
      LTX_AUTH_TOKEN: "reachcut-local-video",
      MPLCONFIGDIR: join(dataDir, "cache", "matplotlib"),
      TORCH_EXTENSIONS_DIR: join(dataDir, "cache", "torch-extensions"),
      PATH: `${dirname(python)}:${process.env.PATH ?? ""}`,
      ...(sdk.status === 0 ? { SDKROOT: sdk.stdout.trim() } : {}),
      PYTHONUNBUFFERED: "1",
    },
    stdio: "inherit",
  },
);
process.exit(result.status ?? 1);

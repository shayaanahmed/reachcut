import { existsSync, mkdirSync } from "node:fs";
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

function run(program, args, cwd = repository) {
  const result = spawnSync(program, args, { cwd, stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

mkdirSync(dirname(engineRoot), { recursive: true });
if (!existsSync(join(engineRoot, ".git"))) {
  run("git", [
    "clone",
    "--depth",
    "1",
    "https://github.com/Lightricks/LTX-Desktop.git",
    engineRoot,
  ]);
}
run("uv", ["sync", "--project", backend]);

console.log("\nLocal LTX engine installed.");
console.log("Next: pnpm video:engine");
console.log(
  "Then open ReachCut Shorts Studio and follow the model-license/download prompt.",
);

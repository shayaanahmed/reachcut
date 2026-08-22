import { spawnSync } from "node:child_process";

const tools = ["ffmpeg", "ffprobe", "uv", "pnpm"];
let failed = false;
for (const tool of tools) {
  const result = spawnSync(tool, ["-version"], { encoding: "utf8" });
  const available = result.status === 0;
  console.log(`${available ? "✓" : "✗"} ${tool}`);
  failed ||= !available;
}

const ollama = await fetch("http://127.0.0.1:11434/api/version").catch(() => null);
console.log(`${ollama?.ok ? "✓" : "!"} Ollama (optional until processing)`);
process.exitCode = failed ? 1 : 0;


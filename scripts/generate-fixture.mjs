import { mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import ffmpegPath from "ffmpeg-static";

mkdirSync("fixtures", { recursive: true });
const args = [
  "-hide_banner", "-nostdin", "-y",
  "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=8",
  "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
  "-metadata", "comment=Programmatically generated CC0 test fixture",
  "fixtures/generated-interview.mp4"
];
const result = spawnSync(ffmpegPath ?? "ffmpeg", args, { stdio: "inherit" });
if (result.error) console.error("FFmpeg is required to generate the fixture.");
process.exitCode = result.status ?? 1;

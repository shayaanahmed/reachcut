import { spawn } from "node:child_process";
import process from "node:process";

const commands = [
  [
    "pnpm",
    [
      "dev:api",
    ],
  ],
  ["pnpm", ["dev:web"]],
];
const children = commands.map(([program, args]) =>
  spawn(program, args, { stdio: "inherit", env: process.env }),
);

let stopping = false;
function stop(signal = "SIGTERM") {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill(signal);
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => stop(signal));
}

for (const child of children) {
  child.on("exit", (code) => {
    stop();
    process.exitCode = code ?? 1;
  });
}

import { copyFile, lstat, mkdir, readlink, readdir } from "node:fs/promises";
import path from "node:path";

async function dereference(source) {
  const visited = new Set();
  let current = path.resolve(source);

  while (true) {
    if (visited.has(current)) {
      throw new Error(`Circular symbolic link detected at ${source}`);
    }
    visited.add(current);

    const metadata = await lstat(current);
    if (!metadata.isSymbolicLink()) return { source: current, metadata };

    const target = await readlink(current);
    current = path.resolve(path.dirname(current), target);
  }
}

async function copyEntry(source, destination, ancestorDirectories) {
  const resolved = await dereference(source);

  if (resolved.metadata.isDirectory()) {
    if (ancestorDirectories.has(resolved.source)) {
      throw new Error(`Circular directory link detected at ${source}`);
    }

    const nextAncestors = new Set(ancestorDirectories);
    nextAncestors.add(resolved.source);
    await mkdir(destination, { recursive: true });
    const entries = await readdir(resolved.source);
    await Promise.all(
      entries.map((entry) =>
        copyEntry(
          path.join(resolved.source, entry),
          path.join(destination, entry),
          nextAncestors,
        ),
      ),
    );
    return;
  }

  if (resolved.metadata.isFile()) {
    await copyFile(resolved.source, destination);
    return;
  }

  throw new Error(`Unsupported staged file type: ${source}`);
}

export async function copyDirectoryDereferenced(source, destination) {
  await copyEntry(source, destination, new Set());
}

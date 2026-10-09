import {
  copyFile,
  cp,
  lstat,
  mkdir,
  readlink,
  readdir,
} from "node:fs/promises";
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

export async function copyPnpmStandaloneDereferenced(source, destination) {
  await copyDirectoryDereferenced(source, destination);

  // Dereferencing apps/web/node_modules/next moves the package out of pnpm's
  // virtual-store directory. Materialize pnpm's hoisted dependency view at the
  // ordinary node_modules root so Node can still resolve Next's dependencies.
  const hoistedDependencies = path.join(
    source,
    "node_modules",
    ".pnpm",
    "node_modules",
  );
  try {
    const metadata = await lstat(hoistedDependencies);
    if (!metadata.isDirectory()) {
      throw new Error(
        `pnpm hoisted dependency directory is invalid: ${hoistedDependencies}`,
      );
    }
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new Error(
        `pnpm hoisted dependency directory is missing: ${hoistedDependencies}`,
      );
    }
    throw error;
  }
  await copyDirectoryDereferenced(
    hoistedDependencies,
    path.join(destination, "node_modules"),
  );
}

export async function copyDirectoryPreservingLinks(source, destination) {
  await cp(source, destination, {
    recursive: true,
    verbatimSymlinks: true,
  });
}

async function validateEntry(root, entry) {
  const metadata = await lstat(entry);

  if (metadata.isSymbolicLink()) {
    const target = await readlink(entry);
    if (path.isAbsolute(target)) {
      throw new Error(
        `Staged symbolic link must be relative: ${entry} -> ${target}`,
      );
    }

    const resolvedTarget = path.resolve(path.dirname(entry), target);
    if (
      resolvedTarget !== root &&
      !resolvedTarget.startsWith(`${root}${path.sep}`)
    ) {
      throw new Error(
        `Staged symbolic link escapes the package: ${entry} -> ${target}`,
      );
    }

    try {
      await lstat(resolvedTarget);
    } catch (error) {
      if (error?.code === "ENOENT") {
        throw new Error(
          `Staged symbolic link is broken: ${entry} -> ${target}`,
        );
      }
      throw error;
    }
    return;
  }

  if (!metadata.isDirectory()) return;
  const entries = await readdir(entry);
  await Promise.all(
    entries.map((name) => validateEntry(root, path.join(entry, name))),
  );
}

export async function validatePortableLinks(directory) {
  const root = path.resolve(directory);
  await validateEntry(root, root);
}

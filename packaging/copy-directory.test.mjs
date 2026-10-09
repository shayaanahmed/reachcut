import assert from "node:assert/strict";
import { createRequire } from "node:module";
import {
  lstat,
  mkdtemp,
  mkdir,
  readlink,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { after, describe, test } from "node:test";

import {
  copyDirectoryDereferenced,
  copyDirectoryPreservingLinks,
  copyPnpmStandaloneDereferenced,
  validatePortableLinks,
} from "./copy-directory.mjs";

describe("dereferenced directory copy", async () => {
  const temporaryRoot = await mkdtemp(
    path.join(os.tmpdir(), "reachcut-copy-test-"),
  );
  after(() => rm(temporaryRoot, { recursive: true, force: true }));

  test(
    "turns file and directory links into regular staged content",
    { skip: process.platform === "win32" && "requires symbolic-link access" },
    async () => {
      const source = path.join(temporaryRoot, "source");
      const destination = path.join(temporaryRoot, "destination");
      const packageDirectory = path.join(source, "packages", "example");
      await mkdir(packageDirectory, { recursive: true });
      await writeFile(
        path.join(packageDirectory, "index.js"),
        "export default 1;\n",
      );
      await symlink("packages/example", path.join(source, "linked-package"));
      await symlink(
        "packages/example/index.js",
        path.join(source, "linked-file.js"),
      );

      await copyDirectoryDereferenced(source, destination);

      assert.equal(
        await readFile(
          path.join(destination, "linked-package", "index.js"),
          "utf8",
        ),
        "export default 1;\n",
      );
      assert.equal(
        await readFile(path.join(destination, "linked-file.js"), "utf8"),
        "export default 1;\n",
      );
      assert.equal(
        (
          await lstat(path.join(destination, "linked-package"))
        ).isSymbolicLink(),
        false,
      );
      assert.equal(
        (
          await lstat(path.join(destination, "linked-file.js"))
        ).isSymbolicLink(),
        false,
      );
    },
  );
});

describe(
  "portable symbolic-link copy",
  { skip: process.platform === "win32" && "POSIX packaging only" },
  async () => {
    const temporaryRoot = await mkdtemp(
      path.join(os.tmpdir(), "reachcut-portable-link-test-"),
    );
    after(() => rm(temporaryRoot, { recursive: true, force: true }));

    test("preserves relative targets without leaking the build path", async () => {
      const source = path.join(temporaryRoot, "source");
      const destination = path.join(temporaryRoot, "destination");
      await mkdir(path.join(source, "packages", "example"), {
        recursive: true,
      });
      await writeFile(
        path.join(source, "packages", "example", "index.js"),
        "export default 1;\n",
      );
      await symlink("packages/example", path.join(source, "linked-package"));

      await copyDirectoryPreservingLinks(source, destination);
      await validatePortableLinks(destination);

      assert.equal(
        await readlink(path.join(destination, "linked-package")),
        "packages/example",
      );
      assert.equal(
        await readFile(
          path.join(destination, "linked-package", "index.js"),
          "utf8",
        ),
        "export default 1;\n",
      );
    });

    test("rejects absolute, escaping, and broken package links", async () => {
      const absoluteRoot = path.join(temporaryRoot, "absolute");
      await mkdir(absoluteRoot);
      await symlink(
        path.join(temporaryRoot, "outside"),
        path.join(absoluteRoot, "link"),
      );
      await assert.rejects(
        validatePortableLinks(absoluteRoot),
        /must be relative/,
      );

      const escapingRoot = path.join(temporaryRoot, "escaping");
      await mkdir(escapingRoot);
      await symlink("../outside", path.join(escapingRoot, "link"));
      await assert.rejects(
        validatePortableLinks(escapingRoot),
        /escapes the package/,
      );

      const brokenRoot = path.join(temporaryRoot, "broken");
      await mkdir(brokenRoot);
      await symlink("missing", path.join(brokenRoot, "link"));
      await assert.rejects(validatePortableLinks(brokenRoot), /is broken/);
    });
  },
);

describe(
  "dereferenced pnpm standalone copy",
  { skip: process.platform === "win32" && "requires symbolic-link access" },
  async () => {
    const temporaryRoot = await mkdtemp(
      path.join(os.tmpdir(), "reachcut-pnpm-copy-test-"),
    );
    after(() => rm(temporaryRoot, { recursive: true, force: true }));

    test("materializes the hoisted dependencies required by linked packages", async () => {
      const source = path.join(temporaryRoot, "source");
      const destination = path.join(temporaryRoot, "destination");
      const virtualStore = path.join(source, "node_modules", ".pnpm");
      const dependency = path.join(
        virtualStore,
        "dependency@1.0.0",
        "node_modules",
        "dependency",
      );
      const packageDirectory = path.join(
        virtualStore,
        "package@1.0.0",
        "node_modules",
        "package",
      );
      const hoistedDependency = path.join(
        virtualStore,
        "node_modules",
        "dependency",
      );
      const applicationModules = path.join(
        source,
        "apps",
        "web",
        "node_modules",
      );
      await mkdir(dependency, { recursive: true });
      await mkdir(packageDirectory, { recursive: true });
      await mkdir(path.dirname(hoistedDependency), { recursive: true });
      await mkdir(applicationModules, { recursive: true });
      await writeFile(
        path.join(dependency, "index.js"),
        "module.exports = 'dependency found';\n",
      );
      await writeFile(
        path.join(packageDirectory, "index.js"),
        "module.exports = require('dependency');\n",
      );
      await symlink(
        path.relative(path.dirname(hoistedDependency), dependency),
        hoistedDependency,
      );
      await symlink(
        path.relative(applicationModules, packageDirectory),
        path.join(applicationModules, "package"),
      );

      await copyPnpmStandaloneDereferenced(source, destination);

      const requireFromApplication = createRequire(
        path.join(destination, "apps", "web", "server.js"),
      );
      assert.equal(requireFromApplication("package"), "dependency found");
      assert.equal(
        (
          await lstat(path.join(destination, "node_modules", "dependency"))
        ).isSymbolicLink(),
        false,
      );
    });
  },
);

import assert from "node:assert/strict";
import {
  lstat,
  mkdtemp,
  mkdir,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { after, describe, test } from "node:test";

import { copyDirectoryDereferenced } from "./copy-directory.mjs";

describe("dereferenced directory copy", async () => {
  const temporaryRoot = await mkdtemp(
    path.join(os.tmpdir(), "reachcut-copy-test-"),
  );
  after(() => rm(temporaryRoot, { recursive: true, force: true }));

  test("turns file and directory links into regular staged content", async () => {
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
      (await lstat(path.join(destination, "linked-package"))).isSymbolicLink(),
      false,
    );
    assert.equal(
      (await lstat(path.join(destination, "linked-file.js"))).isSymbolicLink(),
      false,
    );
  });
});

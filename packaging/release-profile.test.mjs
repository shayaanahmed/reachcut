import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { profileDataDirectory, releaseProfile } from "./release-profile.mjs";

describe("release profiles", () => {
  test("keeps personal and stable installations isolated", () => {
    const stable = releaseProfile("stable");
    const personal = releaseProfile("personal");

    for (const property of [
      "displayName",
      "slug",
      "bundleId",
      "agentId",
      "windowsAppId",
      "localHostname",
      "localPort",
      "internalApiPort",
      "internalWebPort",
    ]) {
      assert.notEqual(personal[property], stable[property], property);
    }
    assert.equal(profileDataDirectory(stable, "darwin"), "ReachCut");
    assert.equal(
      profileDataDirectory(personal, "darwin"),
      "ReachCut Personal",
    );
    assert.equal(
      profileDataDirectory(personal, "linux"),
      "reachcut-personal",
    );
  });

  test("rejects unknown release channels", () => {
    assert.throws(() => releaseProfile("nightly"), /personal or stable/);
  });
});

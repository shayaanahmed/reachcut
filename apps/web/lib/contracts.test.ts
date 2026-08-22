import { describe, expect, it } from "vitest";
import { projectSchema } from "./contracts";

describe("project contract", () => {
  it("rejects an unknown editing plan version", () => {
    expect(() =>
      projectSchema.parse({ clips: [{ plan: { schema_version: "2.0" } }] }),
    ).toThrow();
  });
});

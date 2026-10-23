import { describe, expect, it } from "vitest";
import { errorMessage, responseError } from "./http";

describe("API errors", () => {
  it("explains FastAPI validation errors without echoing submitted input", async () => {
    const error = await responseError(
      new Response(
        JSON.stringify({
          detail: [
            {
              loc: ["body", "title"],
              msg: "String should match pattern",
              input: "private input",
            },
            { loc: ["body", "accounts", 0], msg: "Field required" },
          ],
        }),
        { status: 422 },
      ),
      "Could not save",
    );
    expect(error.message).toBe(
      "title: String should match pattern; accounts.0: Field required",
    );
  });

  it("keeps provider explanations and handles malformed error bodies", async () => {
    expect(errorMessage({ detail: "Reconnect this account" }, "Failed")).toBe(
      "Reconnect this account",
    );
    for (const payload of [null, {}, { detail: {} }, { detail: [null, 1, {}] }])
      expect(errorMessage(payload, "Failed")).toBe("Failed");
    expect(
      (
        await responseError(
          new Response("Bad gateway", { status: 502 }),
          "Could not upload",
        )
      ).message,
    ).toBe("Could not upload (502)");
  });
});

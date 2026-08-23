import { afterEach, describe, expect, it, vi } from "vitest";
import { uploadProject } from "./api";

describe("media upload transport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("bypasses the buffering Next.js rewrite proxy", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "test response" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(uploadProject(new FormData())).rejects.toThrow(
      "test response",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/projects/upload",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

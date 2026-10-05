import { afterEach, describe, expect, it, vi } from "vitest";
import { importProjectUrl, uploadProject } from "../features/projects/api";

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

describe("URL import transport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends URL imports as JSON through the API", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: "test response" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const request = {
      title: "Remote source",
      url: "https://youtube.com/watch?v=abc",
      authorization_confirmed: true,
    };
    await expect(importProjectUrl(request)).rejects.toThrow("test response");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/projects/import-url",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(request),
      }),
    );
  });
});

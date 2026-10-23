import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FrameLibrary } from "./frame-library";
import { studioApi } from "./api";

vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  studioApi: { frames: vi.fn(), sequences: vi.fn(), importFrames: vi.fn() },
}));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(studioApi.frames).mockResolvedValue([]);
  vi.mocked(studioApi.sequences).mockResolvedValue([]);
});
afterEach(cleanup);

it("imports an HTML file and refreshes the library", async () => {
  vi.mocked(studioApi.importFrames).mockResolvedValue({
    frames: 5,
    sequences: 1,
  });
  render(<FrameLibrary />);
  const upload = screen.getByLabelText(/Import HTML frames/);
  const file = new File(["<html></html>"], "sequences.html", {
    type: "text/html",
  });
  fireEvent.change(upload, { target: { files: [file] } });
  expect(
    await screen.findByText("Imported 5 scenes in 1 sequence."),
  ).toBeInTheDocument();
  expect(studioApi.importFrames).toHaveBeenCalledWith(file);
  expect(studioApi.frames).toHaveBeenCalledTimes(2);
  expect(upload).toBeEnabled();
});

it("shows import errors and permits retrying", async () => {
  vi.mocked(studioApi.importFrames).mockRejectedValue(
    new Error("No frame sequences found"),
  );
  render(<FrameLibrary />);
  const upload = screen.getByLabelText(/Import HTML frames/);
  fireEvent.change(upload, {
    target: { files: [new File(["bad"], "bad.html")] },
  });
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "No frame sequences found",
  );
  expect(upload).toBeEnabled();
});

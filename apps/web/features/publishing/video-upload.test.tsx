import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Project } from "../../lib/contracts";
import { PublishingVideoUpload } from "./video-upload";

afterEach(cleanup);

it("offers a Studio upload that opens editing after upload", async () => {
  const project = { id: "uploaded", clips: [{ id: "finished" }] } as Project;
  const created = vi.fn();
  render(
    <PublishingVideoUpload
      destination="studio"
      busy={false}
      onUpload={vi.fn().mockResolvedValue(project)}
      onCreated={created}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "Upload videos to edit" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Video title"), {
    target: { value: "Edit me" },
  });
  fireEvent.submit(
    screen
      .getByRole("button", { name: "Upload and open Studio" })
      .closest("form")!,
  );
  await waitFor(() => expect(created).toHaveBeenCalledWith(project));
});

it("submits a finished video and opens publishing only after a successful upload", async () => {
  const project = { id: "uploaded", clips: [{ id: "finished" }] } as Project;
  const upload = vi.fn().mockResolvedValue(project);
  const created = vi.fn();
  render(
    <PublishingVideoUpload
      busy={false}
      onUpload={upload}
      onCreated={created}
    />,
  );
  const file = new File(["video"], "finished-video.mp4", { type: "video/mp4" });
  fireEvent.change(screen.getByLabelText("Finished video (MP4)"), {
    target: { files: [file] },
  });
  expect(screen.getByLabelText("Video title")).toHaveValue("finished video");
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.submit(
    screen
      .getByRole("button", { name: "Upload and continue to publishing" })
      .closest("form")!,
  );
  await waitFor(() => expect(created).toHaveBeenCalledWith(project));
  const data = upload.mock.calls[0][0] as FormData;
  expect(data.get("title")).toBe("finished video");
  expect(data.get("authorization_confirmed")).toBe("true");
  expect(data.get("media")).toBeInstanceOf(File);
});

it("keeps the form available to retry when uploading fails", async () => {
  const upload = vi.fn().mockResolvedValue(undefined);
  const created = vi.fn();
  render(
    <PublishingVideoUpload
      busy={false}
      onUpload={upload}
      onCreated={created}
    />,
  );
  fireEvent.change(screen.getByLabelText("Video title"), {
    target: { value: "Retry video" },
  });
  fireEvent.submit(
    screen
      .getByRole("button", { name: "Upload and continue to publishing" })
      .closest("form")!,
  );
  await waitFor(() => expect(upload).toHaveBeenCalledOnce());
  expect(created).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Video title")).toHaveValue("Retry video");
});

it("disables controls while uploading", () => {
  render(<PublishingVideoUpload busy onUpload={vi.fn()} onCreated={vi.fn()} />);
  expect(
    screen.getByRole("button", { name: "Uploading video…" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("Finished video (MP4)")).toBeDisabled();
  expect(screen.getByLabelText("Video title")).toBeDisabled();
  expect(screen.getByRole("checkbox")).toBeDisabled();
});

it("uploads multiple videos independently and retries only the failed file", async () => {
  const one = { id: "one", clips: [{ id: "clip-one" }] } as Project;
  const two = { id: "two", clips: [{ id: "clip-two" }] } as Project;
  const upload = vi
    .fn()
    .mockResolvedValueOnce(one)
    .mockResolvedValueOnce(undefined)
    .mockResolvedValueOnce(two);
  const created = vi.fn();
  render(
    <PublishingVideoUpload
      destination="studio"
      busy={false}
      onUpload={upload}
      onCreated={created}
    />,
  );
  const first = new File(["first"], "first-video.mp4", { type: "video/mp4" });
  const second = new File(["second"], "second-video.mp4", {
    type: "video/mp4",
  });
  const input = screen.getByLabelText("Finished video (MP4)");
  expect(input).toHaveAttribute("multiple");
  fireEvent.change(input, { target: { files: [first, second] } });
  fireEvent.change(screen.getByLabelText("Title for second-video.mp4"), {
    target: { value: "Second title" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.submit(
    screen.getByRole("button", { name: "Upload 2 videos" }).closest("form")!,
  );
  await waitFor(() =>
    expect(
      screen.getByText("Upload failed. Retry this video."),
    ).toBeInTheDocument(),
  );
  expect(created).not.toHaveBeenCalled();
  expect(
    screen.getByRole("link", { name: "Edit in Studio →" }),
  ).toHaveAttribute("href", "/projects/one/clips/clip-one");
  const firstData = upload.mock.calls[0][0] as FormData;
  const secondData = upload.mock.calls[1][0] as FormData;
  expect(firstData.get("media")).toBe(first);
  expect(firstData.get("title")).toBe("first video");
  expect(secondData.get("media")).toBe(second);
  expect(secondData.get("title")).toBe("Second title");
  expect(secondData.get("authorization_confirmed")).toBe("true");
  fireEvent.submit(
    screen.getByRole("button", { name: "Upload 1 video" }).closest("form")!,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "All videos uploaded" }),
    ).toBeDisabled(),
  );
  expect(upload).toHaveBeenCalledTimes(3);
  expect((upload.mock.calls[2][0] as FormData).get("media")).toBe(second);
  expect(
    screen.getAllByRole("link", { name: "Edit in Studio →" }),
  ).toHaveLength(2);
});

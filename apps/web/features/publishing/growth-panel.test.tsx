import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GrowthPanel } from "./growth-panel";
import {
  generateGrowth,
  loadGrowth,
  saveGrowth,
  type GrowthBrief,
} from "./growth-api";

vi.mock("./growth-api", () => ({
  generateGrowth: vi.fn(),
  loadGrowth: vi.fn(),
  saveGrowth: vi.fn(),
  prepareGrowth: vi.fn(),
}));
afterEach(cleanup);
const brief: GrowthBrief = {
  automatic: false,
  account_id: null,
  profile: { audience: "", niche: "", language: "", country: "" },
  target_query: "",
  evidence: [],
  creative: null,
};
const creative: GrowthBrief["creative"] = {
  openings: [1, 2, 3].map((i) => ({
    opening_line: `Opening ${i}`,
    first_frame: `Frame ${i}`,
  })),
  packages: [
    {
      platform: "youtube",
      title: "Local AI",
      caption: "Run AI locally",
      cover_text: "Local AI",
      hashtags: ["#LocalAI"],
    },
  ],
  experiment: "Compare opening clarity across similar posts",
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(loadGrowth).mockResolvedValue({
    automatic_enabled: false,
    preparation: null,
    brief,
    profiles: {},
    diagnoses: [],
  });
  vi.mocked(generateGrowth).mockImplementation(async (_, input) => ({
    ...input,
    creative,
  }));
  vi.mocked(saveGrowth).mockImplementation(async (_, input) => input);
});

describe("growth brief", () => {
  it("lets users review generated copy, save it, and explicitly apply it", async () => {
    const apply = vi.fn();
    render(<GrowthPanel clipId="clip-1" accounts={[]} onApply={apply} />);
    const query = await screen.findByLabelText("Target search query");
    fireEvent.click(
      screen.getByText("Advanced audience, evidence & publishing copy"),
    );
    fireEvent.change(query, { target: { value: "Run AI locally" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Generate growth draft" }),
    );
    await screen.findByText("Opening 1");
    expect(generateGrowth).toHaveBeenCalledWith(
      "clip-1",
      expect.objectContaining({ target_query: "Run AI locally" }),
    );
    expect(saveGrowth).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Save brief & audience" }),
    );
    await screen.findByText("Growth brief saved.");
    fireEvent.click(
      screen.getByRole("button", { name: "Use reviewed copy in publisher" }),
    );
    await waitFor(() => expect(apply).toHaveBeenCalledWith(creative!.packages));
  });
  it("keeps saved inputs available when generation fails", async () => {
    vi.mocked(generateGrowth).mockRejectedValue(
      new Error("Local model unavailable"),
    );
    render(<GrowthPanel clipId="clip-1" accounts={[]} onApply={vi.fn()} />);
    await screen.findByLabelText("Target search query");
    fireEvent.click(
      screen.getByText("Advanced audience, evidence & publishing copy"),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Generate growth draft" }),
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Local model unavailable",
    );
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Save brief & audience",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
  });
});

it("automatically applies a prepared brief without manual field entry or confirmation", async () => {
  vi.mocked(loadGrowth).mockResolvedValue({
    automatic_enabled: true,
    preparation: { status: "ready", error: null, reasoning: "Clear opening" },
    brief: {
      ...brief,
      automatic: true,
      profile: { ...brief.profile, audience: "Developers" },
      target_query: "Local AI",
      creative,
    },
    profiles: {},
    diagnoses: [],
  });
  const apply = vi.fn();
  render(<GrowthPanel clipId="clip-1" accounts={[]} onApply={apply} />);
  await waitFor(() => expect(apply).toHaveBeenCalledWith(creative!.packages));
  expect(
    (
      screen
        .getByText("Advanced audience, evidence & publishing copy")
        .closest("details") as HTMLDetailsElement
    ).open,
  ).toBe(false);
  expect(screen.getByText(/AI optimization ready/)).toBeTruthy();
});

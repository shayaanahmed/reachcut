import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getOAuthAccountSelection, selectOAuthAccount } from "./api";
import { AccountConnectionPicker } from "./account-connection-picker";

vi.mock("./api", () => ({
  getOAuthAccountSelection: vi.fn(),
  selectOAuthAccount: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState(
    null,
    "",
    "/settings/accounts?connection_selection=opaque-selection",
  );
  vi.mocked(getOAuthAccountSelection).mockResolvedValue({
    platform: "instagram",
    candidates: [
      {
        external_account_id: "ig-1",
        display_name: "First profile",
        username: "first",
        parent_page_name: "First Page",
        already_connected: true,
      },
      {
        external_account_id: "ig-2",
        display_name: "Second profile",
        username: "second",
        parent_page_name: "Second Page",
        already_connected: false,
      },
    ],
  });
});
afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

describe("OAuth destination selection", () => {
  it("requires an explicit choice and connects the second profile", async () => {
    vi.mocked(selectOAuthAccount).mockResolvedValue({
      id: "account-2",
      label: "Second profile",
      username: "second",
    } as Awaited<ReturnType<typeof selectOAuthAccount>>);
    const connected = vi.fn().mockResolvedValue(undefined);
    render(<AccountConnectionPicker onConnected={connected} />);
    const button = await screen.findByRole("button", {
      name: "Connect selected destination",
    });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(
      screen
        .getAllByRole("radio")
        .every((radio) => !(radio as HTMLInputElement).checked),
    ).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: /Second profile/ }));
    fireEvent.click(button);
    await waitFor(() => expect(connected).toHaveBeenCalledOnce());
    expect(selectOAuthAccount).toHaveBeenCalledWith("opaque-selection", "ig-2");
    expect(window.location.search).not.toContain("connection_selection");
  });

  it("keeps the chooser visible when saving fails", async () => {
    vi.mocked(selectOAuthAccount).mockRejectedValue(
      new Error("Selection expired. Connect again."),
    );
    render(<AccountConnectionPicker onConnected={vi.fn()} />);
    fireEvent.click(
      await screen.findByRole("radio", { name: /Second profile/ }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Connect selected destination" }),
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Selection expired",
    );
    expect(
      screen.getByRole("heading", {
        name: "Choose the destination to connect",
      }),
    ).toBeTruthy();
  });

  it("shows expiry errors without selecting a fallback account", async () => {
    vi.mocked(getOAuthAccountSelection).mockRejectedValue(
      new Error("Authorization expired"),
    );
    render(<AccountConnectionPicker onConnected={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Authorization expired",
    );
    expect(selectOAuthAccount).not.toHaveBeenCalled();
  });
});

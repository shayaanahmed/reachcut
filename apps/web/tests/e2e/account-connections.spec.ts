import { expect, test } from "@playwright/test";

const date = "2026-10-16T10:00:00Z";
const account = {
  id: "account-2",
  platform: "instagram",
  label: "Second Instagram",
  username: "second.profile",
  external_account_id: "ig-2",
  parent_page_name: "Second Facebook Page",
  profile_url: "https://www.instagram.com/second.profile/",
  default_hashtags: [],
  default_cta: "",
  default_campaign_url: null,
  currency: "EUR",
  connection_status: "connected",
  is_default: true,
  is_active: true,
  created_at: date,
  updated_at: date,
};

test("chooses the intended Instagram profile after a multi-Page login", async ({
  page,
}) => {
  let connected = false;
  await page.route("**/api/social-accounts", (route) =>
    route.fulfill({ json: connected ? [account] : [] }),
  );
  await page.route("**/api/social-accounts/readiness", (route) =>
    route.fulfill({
      json: connected
        ? [
            {
              account_id: account.id,
              platform: "instagram",
              provider_configured: true,
              credentials_available: true,
              publishing_ready: true,
              issues: [],
            },
          ]
        : [],
    }),
  );
  await page.route("**/api/publishing/capabilities", (route) =>
    route.fulfill({
      json: {
        configured_platforms: ["instagram", "facebook"],
        provider_setup: [],
      },
    }),
  );
  await page.route(
    "**/api/social-account-selections/selection-token",
    async (route) => {
      if (route.request().method() === "POST") {
        expect(route.request().postDataJSON()).toEqual({
          external_account_id: "ig-2",
        });
        connected = true;
        await route.fulfill({ json: account });
      } else
        await route.fulfill({
          json: {
            platform: "instagram",
            candidates: [
              {
                external_account_id: "ig-1",
                display_name: "First Instagram",
                username: "first.profile",
                parent_page_name: "First Facebook Page",
                already_connected: true,
              },
              {
                external_account_id: "ig-2",
                display_name: "Second Instagram",
                username: "second.profile",
                parent_page_name: "Second Facebook Page",
                already_connected: false,
              },
            ],
          },
        });
    },
  );
  await page.goto("/settings/accounts?connection_selection=selection-token");
  await expect(
    page.getByRole("heading", { name: "Choose the destination to connect" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Connect selected destination" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("radio", { name: /First Instagram/ }),
  ).not.toBeChecked();
  await page.screenshot({
    path: "/tmp/reachcut-account-picker-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "/tmp/reachcut-account-picker-mobile.png",
    fullPage: true,
  });
  await page.getByRole("radio", { name: /Second Instagram/ }).check();
  await page
    .getByRole("button", { name: "Connect selected destination" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Second Instagram", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Account ID: ig-2", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Facebook Page: Second Facebook Page", { exact: true }),
  ).toBeVisible();
  expect(page.url()).not.toContain("connection_selection");
});

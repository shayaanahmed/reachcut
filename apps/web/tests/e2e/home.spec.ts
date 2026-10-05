import { expect, test } from "@playwright/test";

test("shows the tool dashboard and local project workflow", async ({
  page,
}) => {
  await page.route("**/api/projects", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Your content workspace" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "New project" })).toBeVisible();
  await expect(page.getByText("Local processing")).toBeVisible();
});

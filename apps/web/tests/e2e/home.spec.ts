import { expect, test } from "@playwright/test";

test("requires media authorization", async ({ page }) => {
  await page.route("http://127.0.0.1:8000/api/projects", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Find the moment. Keep the meaning." }),
  ).toBeVisible();
  await expect(
    page.getByText(/I own, license, or have permission/),
  ).toBeVisible();
});

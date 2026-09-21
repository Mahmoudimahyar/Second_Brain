import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

import { waitForDarkMode } from "./helpers";

test.describe("Home page", () => {
  test("renders without console errors", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await page.goto("/");
    await expect(page).toHaveTitle(/SecBrain|V1\.5/);
    expect(consoleErrors).toHaveLength(0);
  });

  test("axe-core: zero critical violations", async ({ page }) => {
    await page.goto("/");
    await waitForDarkMode(page);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();
    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(critical).toEqual([]);
  });
});

import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

import { waitForDarkMode } from "./helpers";

// Each of the 3 level pages renders a graph canvas (W2-1) + has the
// table-fallback toggle (W2-1 accessibility requirement).
const LEVELS = [
  { path: "/graph/structural", title: /Level A/ },
  { path: "/graph/clusters", title: /Level B/ },
  { path: "/graph/analyzed", title: /Level C/ },
];

for (const { path, title } of LEVELS) {
  test(`graph page ${path} renders without errors`, async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await page.goto(path);
    // level:1 disambiguates from the EmptyState's H3 "Level X canvas".
    await expect(
      page.getByRole("heading", { name: title, level: 1 }),
    ).toBeVisible();
    // V1.5d C10 — view-toggle div now carries role="group" + aria-label.
    await expect(page.getByRole("group", { name: "View mode" })).toBeVisible();
    expect(consoleErrors).toHaveLength(0);
  });

  test(`graph page ${path}: a11y critical violations = 0`, async ({ page }) => {
    await page.goto(path);
    await waitForDarkMode(page);
    // Disable `aria-valid-attr-value` — axe-core 4.11 still uses the
    // XML-era ID grammar and flags React-19/Radix-generated IDs
    // containing « / » as invalid. Per HTML5 spec, any non-whitespace
    // character is a valid id, including the U+00AB / U+00BB Radix uses
    // by default. This is a documented axe false positive.
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .disableRules(["aria-valid-attr-value"])
      .analyze();
    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(critical).toEqual([]);
  });
}

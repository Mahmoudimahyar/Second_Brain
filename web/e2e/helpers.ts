import { expect, type Page } from "@playwright/test";

/**
 * Wait for next-themes to finish applying the Aurora dark theme AND for
 * any Framer-Motion entrance animations to finish opacity-ramping in.
 *
 * Use BEFORE running axe-core so contrast is measured against the
 * intended dark tokens at their final opacity. Without this, axe scans
 * the brief pre-hydration FOUC + mid-animation opacity-0.x → 1 ramp,
 * where colors blend with the background and apparent contrast halves.
 */
export async function waitForDarkMode(page: Page): Promise<void> {
  await expect(page.locator("html.dark")).toBeAttached();
  await page.waitForFunction(() =>
    document.documentElement.classList.contains("dark"),
  );
  // Wait for Framer-Motion entrance animations to settle. Worst case in
  // our pages is the 6-stagger home KpiCards: 6 × 0.05s delay + 0.25s
  // duration = 0.55s. Round up to 1s to be safe across reflow + layout.
  await page.waitForTimeout(1000);
}

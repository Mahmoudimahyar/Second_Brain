/**
 * V1.6a Phase 9 — Playwright e2e for /ingest/web/*.
 *
 * Failing-first per V1.6a plan.md Phase 9: registration wizard happy
 * path. axe-core per page load.
 *
 * The backend is mocked at the route level (Playwright network
 * interception) so the tests don't need the FastAPI service running.
 */

import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

import { waitForDarkMode } from "./helpers";

const API_BASE = "**/api/v1/ingest/web/**";

test.beforeEach(async ({ page }) => {
  // Default: return an empty domain list so the list page renders its
  // empty state. Individual tests override per-route via add'l routes.
  await page.route("**/api/v1/ingest/web/domains?status=active", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ domains: [], total: 0 }),
    });
  });
});

test.describe("/ingest/web", () => {
  test("list page renders empty state with CTA", async ({ page }) => {
    await page.goto("/ingest/web");
    await waitForDarkMode(page);
    await expect(
      page.getByRole("heading", { name: /Website crawls/i, level: 1 }),
    ).toBeVisible();
    await expect(page.getByText(/No crawl domains registered yet/i)).toBeVisible();
    // Two CTAs on the page (header + empty state) — both go to /register.
    await expect(page.getByRole("link", { name: /Register/i }).first()).toBeVisible();
  });

  test("axe-core: zero critical violations on list page", async ({ page }) => {
    await page.goto("/ingest/web");
    await waitForDarkMode(page);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .disableRules(["aria-valid-attr-value"])
      .analyze();
    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(critical).toEqual([]);
  });
});

test.describe("/ingest/web/register", () => {
  test("registration wizard happy path", async ({ page }) => {
    // Mock the POST.
    await page.route(
      "**/api/v1/ingest/web/domains",
      async (route, request) => {
        if (request.method() !== "POST") {
          await route.continue();
          return;
        }
        const body = request.postDataJSON() as { domain: string };
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            domain_id: "web:test123",
            domain: body.domain,
            tier: "L2",
            stage: "L1",
            cadence_cron: "0 6 * * *",
            status: "active",
            max_pages_per_run: 500,
            max_pages_per_month: 5000,
            max_usd_per_month: 5.0,
            concurrency: 4,
            enable_ocr: false,
            enable_scrapingbee: false,
            confirm_l1: false,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            created_by: "ui",
            notes: null,
          }),
        });
      },
    );
    // Mock the detail page's queries since the wizard redirects to
    // /ingest/web/web:test123 on success.
    await page.route("**/api/v1/ingest/web/domains/web%3Atest123", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          domain_id: "web:test123",
          domain: "www.adea.org",
          tier: "L2",
          stage: "L1",
          cadence_cron: "0 6 * * *",
          status: "active",
          max_pages_per_run: 500,
          max_pages_per_month: 5000,
          max_usd_per_month: 5.0,
          concurrency: 4,
          enable_ocr: false,
          enable_scrapingbee: false,
          confirm_l1: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          created_by: "ui",
          notes: null,
        }),
      });
    });
    await page.route(
      "**/api/v1/ingest/web/domains/web%3Atest123/jobs",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ jobs: [], total: 0 }),
        });
      },
    );
    await page.route(
      "**/api/v1/ingest/web/domains/web%3Atest123/budget",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            domain_id: "web:test123",
            spent_month_usd: 0,
            cap_usd: 5.0,
            projected_next_run_usd: null,
          }),
        });
      },
    );

    await page.goto("/ingest/web/register");
    await waitForDarkMode(page);
    await expect(
      page.getByRole("heading", { name: /Register a crawl domain/i }),
    ).toBeVisible();

    // Fill the required field.
    await page.getByLabel(/FQDN/i).fill("www.adea.org");
    // Submit.
    await page.getByRole("button", { name: /Register & start first crawl/i }).click();
    // The wizard navigates to the domain detail page on success.
    await expect(page).toHaveURL(/\/ingest\/web\/web%3Atest123/);
  });

  test("axe-core: zero critical violations on register page", async ({ page }) => {
    await page.goto("/ingest/web/register");
    await waitForDarkMode(page);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .disableRules(["aria-valid-attr-value"])
      .analyze();
    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(critical).toEqual([]);
  });
});

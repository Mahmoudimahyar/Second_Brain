import { expect, test } from "@playwright/test";

// V1.5d C10 — re-target the W2-3 engine-form selectors to the
// redesigned components. The forms now use Radix `<Select>` for the
// tier picker (not native `<select>`), so opening + picking L1 has to
// click the option element rather than calling `selectOption`.

const FORMS = [
  { path: "/ingest/new/postgres", title: /PostgreSQL/i },
  { path: "/ingest/new/mysql", title: /MySQL/i },
  { path: "/ingest/new/neo4j", title: /Neo4j/i },
  { path: "/ingest/new/upload", title: /Upload files/i },
];

for (const { path, title } of FORMS) {
  test(`engine form ${path} renders`, async ({ page }) => {
    await page.goto(path);
    // level:1 disambiguates from the H3 notes-section heading the
    // engine pages render under the form.
    await expect(
      page.getByRole("heading", { name: title, level: 1 }),
    ).toBeVisible();
  });
}

test("Postgres form has tier picker + L1 confirmation gate", async ({
  page,
}) => {
  await page.goto("/ingest/new/postgres");
  // Radix `<Select>` trigger exposes as `combobox`; the default selection
  // text shows the L2 label.
  const tierTrigger = page.getByRole("combobox").filter({ hasText: /L2/i });
  await expect(tierTrigger).toBeVisible();
  // Open the dropdown + click the L1 option.
  await tierTrigger.click();
  await page.getByRole("option", { name: /L1/i }).click();
  // The L1 confirmation card now renders.
  await expect(
    page.getByRole("region", { name: /L1 tier confirmation/i }),
  ).toBeVisible();
  await expect(
    page.getByText(/immutable ground truth/i).first(),
  ).toBeVisible();
});

import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { fixture, resetDatabase } from "./helpers";

const expected = JSON.parse(readFileSync(fixture("expected_results.json"), "utf8")).figures;
const inr = (paise: number) =>
  `₹${new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(paise / 100)}`;

test.beforeEach(async ({ request }) => {
  resetDatabase();
  const res = await request.post("/api/sample");
  expect(res.ok()).toBeTruthy();
});

test("overview shows exactly four things, with the sample's net worth", async ({ page }) => {
  await page.goto("/");
  const main = page.getByRole("main");
  for (const name of ["Net worth", "This month", "Safe to spend", "Inbox"]) {
    await expect(main.getByRole("region", { name })).toBeVisible();
  }
  await expect(main.getByRole("region")).toHaveCount(4);
  await expect(main.getByRole("region", { name: "Net worth" })).toContainText(inr(expected.net_worth));
  await main.getByText("How is this worked out?").click();
  await expect(main.getByRole("region", { name: "Safe to spend" })).toContainText("Owed on credit cards");
});

test("spending shows the month, its categories and the check line", async ({ page }) => {
  await page.goto("/spending?month=2026-09");
  await expect(page.getByRole("heading", { name: "Spending", exact: true })).toBeVisible();
  await expect(page.getByText("September 2026")).toBeVisible();
  await expect(page.getByRole("region", { name: "Spent" })).toContainText(inr(expected.spent));
  await expect(page.getByText(/Net worth changed by .* ✓/)).toBeVisible();
  await page.getByRole("link", { name: /Housing/ }).click();
  await expect(page).toHaveURL(/\/transactions\?category_id=/);
});

test("transactions read From → To and open to their bookkeeping", async ({ page }) => {
  await page.goto("/transactions");
  await page.getByPlaceholder("Search").fill("SALARY");
  const row = page.getByRole("row").filter({ hasText: "Testcorp Salary" }).first();
  await expect(row).toContainText("Salary");
  await expect(row).toContainText("Sample HDFC Savings");
  await row.getByRole("button", { name: "Show bookkeeping" }).click();
  await expect(page.getByText("Income:Salary")).toBeVisible();
});

test("categories can be added, described and merged", async ({ page }) => {
  await page.goto("/categories");
  await page.getByRole("button", { name: "＋ Add category" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Gym");
  await page.getByLabel("What is it for?").fill("Memberships");
  await page.getByRole("button", { name: "Add category" }).click();
  const moneyOut = page.getByRole("region", { name: "Money out" });
  await expect(moneyOut).toContainText("Gym");
  const gym = moneyOut.getByRole("listitem").filter({ hasText: "Memberships" });
  await gym.getByRole("button", { name: "Merge Gym" }).click();
  await page.getByRole("dialog").getByLabel("Merge into").selectOption({ label: "Health" });
  await page.getByRole("dialog").getByRole("button", { name: "Merge" }).click();
  await expect(moneyOut).not.toContainText("Memberships");
});

test("a monthly allowance caps safe to spend", async ({ page }) => {
  await page.goto("/settings");
  const limits = page.getByRole("region", { name: "Safe to spend" });
  await limits.getByLabel("Monthly allowance ₹").fill("5000");
  await limits.getByRole("button", { name: "Save" }).click();
  await expect(limits.getByRole("status")).toHaveText("Saved");
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Safe to spend" })).toContainText("₹5,000.00");
});

test("all accounts use real accounting terms", async ({ page }) => {
  await page.goto("/accounts");
  for (const kind of ["Assets", "Liabilities", "Income", "Expenses"]) {
    await expect(page.getByRole("heading", { name: kind })).toBeVisible();
  }
});

test("on a phone the sidebar is a drawer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await page.getByRole("link", { name: "Spending" }).click();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
});

test("Ask opens the assistant beside the page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Ask" }).click();
  const panel = page.getByRole("complementary", { name: "Assistant" });
  await expect(panel).toContainText("How much can I safely spend this month?");
  await expect(page.getByRole("region", { name: "Net worth" })).toBeVisible();
  await panel.getByRole("button", { name: "Close assistant" }).click();
  await expect(panel).toBeHidden();
});

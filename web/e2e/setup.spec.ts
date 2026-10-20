import { expect, test } from "@playwright/test";
import { resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test("a new person is walked through setup before adding statements", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Your name").fill("Asha Rao");
  await page.getByRole("button", { name: "Get started" }).click();

  await expect(page).toHaveURL(/\/setup/);
  await expect(page.getByText("Step 1 of 4")).toBeVisible();
  await expect(page.getByText("Let's set up your books. It takes about two minutes.")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("Add the accounts you want to track. Statements are uploaded into these.")).toBeVisible();
  const continueButton = page.getByRole("button", { name: "Continue" });
  await expect(continueButton).toBeDisabled();
  await page.getByLabel("Type").selectOption("savings");
  await page.getByLabel("Bank or provider").selectOption("HDFC Bank");
  await page.getByLabel("Name").fill("HDFC Savings");
  await page.getByRole("button", { name: "Add account" }).click();
  await expect(page.getByRole("list", { name: "Accounts added" })).toContainText("HDFC Savings");
  await continueButton.click();

  await expect(page.getByText("Step 3 of 4")).toBeVisible();
  await expect(page.getByRole("region", { name: "Money out" })).toContainText("Restaurants, cafés, food delivery");
  await page.getByRole("button", { name: "＋ Add category" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Gym");
  await page.getByLabel("What is it for?").fill("Memberships and classes at gyms");
  await page.getByRole("button", { name: "Add category" }).click();
  await expect(page.getByRole("region", { name: "Money out" })).toContainText("Memberships and classes at gyms");
  await page.getByRole("button", { name: "Use these categories" }).click();

  await expect(page.getByText("You're set up. Add a statement to see your numbers.")).toBeVisible();
  await page.getByRole("button", { name: "Add your first statement" }).click();
  await expect(page).toHaveURL(/\/accounts\/.+\?upload=1/);
  await expect(page.getByRole("dialog", { name: "Upload a statement" })).toBeVisible();
  await page.keyboard.press("Escape");
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link", { name: /HDFC Savings/ })).toBeVisible();
  await expect(nav).toContainText("Cash and savings");
});

test("setup cannot be skipped: an unfinished ledger always lands back on it", async ({ page, request }) => {
  const res = await request.post("/api/people", { data: { name: "Ben Mills" } });
  expect(res.ok()).toBeTruthy();
  await page.goto("/transactions");
  await expect(page).toHaveURL(/\/setup/);
});

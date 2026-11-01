import { expect, type Page, test } from "@playwright/test";
import { completeSetup, createAccount, createPerson, fixture, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

async function chooseCategory(page: Page, row: ReturnType<Page["locator"]>, name: string) {
  await row.getByRole("button", { name: /category/i }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByPlaceholder("Search categories").fill(name);
  await dialog.getByRole("button", { name: new RegExp(`^${name}`) }).first().click();
  await expect(dialog).toBeHidden();
}

/** With a model the bill payment may already be an own-account move; without one it waits for
 * a category. Either way it ends up as an own-account move. */
async function makeOwnMove(page: Page, text: RegExp) {
  const inbox = page.getByRole("list", { name: "Inbox" });
  const row = inbox.getByRole("listitem").filter({ hasText: text }).first();
  await expect(row).toBeVisible();
  if (await row.getByRole("button", { name: /category/i }).isVisible().catch(() => false)) {
    await chooseCategory(page, row, "Own account or investment");
  }
}

test("upload, fix the inbox, pair a card payment, and remove a statement", async ({ page, request }) => {
  const person = await createPerson(request);
  const savings = await createAccount(request, person, { name: "HDFC Savings", type: "savings", institution: "HDFC Bank" });
  const card = await createAccount(request, person, { name: "HDFC Card", type: "credit_card", institution: "HDFC Bank" });
  await completeSetup(request, person);

  await page.goto(`/accounts/${savings}?upload=1`);
  const dialog = page.getByRole("dialog", { name: "Upload a statement" });
  await dialog.getByLabel("Statement file").setInputFiles(fixture("hdfc_bank_sep.csv"));
  await dialog.getByRole("button", { name: "Upload" }).click();
  await expect(dialog).toContainText("9 rows added");
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("heading", { name: "HDFC Savings" })).toBeVisible();
  await expect(page.getByText("₹1,92,455.50").first()).toBeVisible();

  await page.getByRole("link", { name: /Inbox/ }).click();
  const inbox = page.getByRole("list", { name: "Inbox" });
  await expect(inbox.getByRole("listitem").first()).toBeVisible();
  await makeOwnMove(page, /BILLPAY|Card bill|16,268/);
  await expect(inbox).toContainText("₹16,268.00 left HDFC Savings for an account of yours");

  const badge = page.getByRole("navigation", { name: "Main" }).getByLabel(/to do/);
  const before = Number(await badge.textContent());
  const grocer = inbox.getByRole("listitem").filter({ hasText: /GROCER|Grocer/i }).first();
  if (await grocer.getByRole("button", { name: /category/i }).isVisible().catch(() => false)) {
    await chooseCategory(page, grocer, "Groceries");
    await expect(badge).toHaveText(String(before - 1));
  }

  await page.goto(`/accounts/${card}`);
  await page.getByRole("button", { name: "Upload statement" }).first().click();
  await page.getByRole("dialog").getByLabel("Statement file").setInputFiles(fixture("hdfc_card_sep.xlsx"));
  await page.getByRole("dialog").getByRole("button", { name: "Upload" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Done" }).click();

  // The starter rules recognise the card's "payment received" line as an own-account move, so it
  // pairs with the bank payment by itself and nothing is left to fix in the inbox.
  await page.goto("/inbox");
  await expect(page.getByText("₹16,268.00 left HDFC Savings")).toHaveCount(0);
  await expect(page.getByText(/BPPY/)).toHaveCount(0);

  await page.goto(`/accounts/${card}`);
  await page.getByRole("tab", { name: "Statements" }).click();
  await page.getByRole("button", { name: /Remove/ }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Remove statement" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByRole("list", { name: "Statements" })).toBeHidden();
  await page.goto("/inbox");
  await expect(inbox).toContainText("₹16,268.00 left HDFC Savings for an account of yours");
});

test("an account with no statements says how to start", async ({ page, request }) => {
  const person = await createPerson(request);
  const savings = await createAccount(request, person, { name: "HDFC Savings", type: "savings", institution: "HDFC Bank" });
  await completeSetup(request, person);
  await page.goto(`/accounts/${savings}`);
  await expect(page.getByText("Upload your first HDFC Savings statement")).toBeVisible();
  await page.goto("/inbox");
  await expect(page.getByText("All caught up.")).toBeVisible();
});

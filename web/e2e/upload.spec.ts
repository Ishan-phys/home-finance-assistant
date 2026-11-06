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

test("an account added twice can be deleted, and the other one stays", async ({ page, request }) => {
  const person = await createPerson(request);
  const keep = await createAccount(request, person, { name: "SBI Savings", type: "savings", institution: "State Bank of India" });
  const extra = await createAccount(request, person, { name: "SBI Savings", type: "savings", institution: "State Bank of India" });
  await completeSetup(request, person);

  await page.goto(`/accounts/${extra}`);
  await page.getByRole("button", { name: "Delete account" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("0 transactions");
  await expect(dialog).toContainText("0 uploaded statements");
  await dialog.getByRole("button", { name: "Delete account" }).click();

  await expect(page).toHaveURL(/\/accounts$/);
  await expect(page.locator(`a[href="/accounts/${extra}"]`)).toHaveCount(0);
  await expect(page.locator(`a[href="/accounts/${keep}"]`).first()).toBeVisible();
});

async function setUpBillPayment(page: Page, request: Parameters<typeof createPerson>[0]) {
  const person = await createPerson(request);
  const savings = await createAccount(request, person, { name: "HDFC Savings", type: "savings", institution: "HDFC Bank" });
  await createAccount(request, person, { name: "Axis Flipkart", type: "credit_card", institution: "Axis Bank" });
  await createAccount(request, person, { name: "HDFC Swiggy", type: "credit_card", institution: "HDFC Bank" });
  await completeSetup(request, person);
  await page.goto(`/accounts/${savings}?upload=1`);
  const dialog = page.getByRole("dialog", { name: "Upload a statement" });
  await dialog.getByLabel("Statement file").setInputFiles(fixture("hdfc_bank_sep.csv"));
  await dialog.getByRole("button", { name: "Upload" }).click();
  await expect(dialog).toContainText("9 rows added");
  await dialog.getByRole("button", { name: "Done" }).click();
  await page.goto("/inbox");
  await makeOwnMove(page, /BILLPAY|Card bill|16,268/);
  return page.getByRole("list", { name: "Inbox" }).getByRole("listitem").filter({ hasText: "₹16,268.00 left HDFC Savings" });
}

test("pay a card from the inbox: a wrong pick is undone, the right one is recorded", async ({ page, request }) => {
  const row = await setUpBillPayment(page, request);
  await expect(row).toBeVisible();

  // The wrong card by mistake: the row leaves the inbox and an Undo appears.
  await row.getByRole("button", { name: "Pay a card" }).click();
  const dialog = page.getByRole("dialog", { name: "Which card did this pay?" });
  await dialog.getByRole("button", { name: /HDFC Swiggy/ }).click();
  const note = page.getByRole("status");
  await expect(note).toContainText("₹16,268.00 recorded as a payment to HDFC Swiggy");
  await expect(note).toContainText("You can undo this for");
  await expect(row).toHaveCount(0);

  // Undo puts it back exactly as it was.
  await note.getByRole("button", { name: "Undo" }).click();
  await expect(note).toContainText("Undone");
  await expect(row).toBeVisible();

  // The right card. The Transactions page then says the payment is waiting for the statement.
  await row.getByRole("button", { name: "Pay a card" }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Axis Flipkart/ }).click();
  await expect(page.getByRole("status")).toContainText("recorded as a payment to Axis Flipkart");
  await expect(row).toHaveCount(0);
  await page.goto("/transactions");
  await expect(page.getByText("Paid to Axis Flipkart · awaiting statement")).toBeVisible();
});

test("the offer to undo a card payment ends after 45 seconds", async ({ page, request }) => {
  await page.clock.install();
  const row = await setUpBillPayment(page, request);
  await row.getByRole("button", { name: "Pay a card" }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Axis Flipkart/ }).click();
  const note = page.getByRole("status");
  await expect(note.getByRole("button", { name: "Undo" })).toBeVisible();
  await page.clock.fastForward(30_000);
  await expect(note.getByRole("button", { name: "Undo" })).toBeVisible();
  await page.clock.fastForward(20_000);
  await expect(note).toHaveCount(0);
  await page.goto("/transactions");
  await expect(page.getByText("Paid to Axis Flipkart · awaiting statement")).toBeVisible();
});

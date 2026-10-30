import { expect, test } from "@playwright/test";
import { completeSetup, createAccount, createPerson, fixture, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test("the Rules page lists the starter rules and adds one", async ({ page, request }) => {
  const person = await createPerson(request);
  await createAccount(request, person, { name: "HDFC Savings", type: "savings", institution: "HDFC Bank" });
  await completeSetup(request, person);
  await page.goto("/rules");
  await expect(page.getByRole("heading", { name: "Rules" })).toBeVisible();
  const list = page.getByRole("list", { name: "Rules" });
  await expect(list).toContainText("Card bill payment");
  await expect(list).toContainText("starter");

  await page.getByRole("button", { name: /Add rule/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Text").fill("Vikram Kapoor");
  await dialog.getByLabel("Category").selectOption({ label: "Housing" });
  await dialog.getByLabel("Name (optional)").fill("Rent");
  await expect(dialog).toContainText("Matches 0 existing transactions");
  await dialog.getByRole("button", { name: "Add rule" }).click();
  await expect(dialog).toBeHidden();
  await expect(list).toContainText("Rent");
  await expect(list).toContainText("contains “Vikram Kapoor”");
  await expect(list).toContainText("Housing");

  await page.getByRole("button", { name: "Delete Rent" }).click();
  await expect(list).not.toContainText("Vikram Kapoor");
});

test("the bank narration is shown, and choosing a category can become a rule", async ({ page, request }) => {
  const person = await createPerson(request);
  const savings = await createAccount(request, person, { name: "HDFC Savings", type: "savings", institution: "HDFC Bank" });
  await completeSetup(request, person);
  await page.goto(`/accounts/${savings}?upload=1`);
  const upload = page.getByRole("dialog", { name: "Upload a statement" });
  await upload.getByLabel("Statement file").setInputFiles(fixture("hdfc_bank_sep.csv"));
  await upload.getByRole("button", { name: "Upload" }).click();
  await expect(upload).toContainText("9 rows added");
  await upload.getByRole("button", { name: "Done" }).click();

  await page.goto("/inbox");
  const inbox = page.getByRole("list", { name: "Inbox" });
  // REF000009 is a reference number: redaction removes it from the stored text, so seeing it here
  // means the sealed original is being read back.
  const row = inbox.getByRole("listitem").filter({ hasText: "REF000009" }).first();
  await expect(row).toContainText("UPI-TEST CAFE-TESTCAFE-REF000009-UPI");
  await row.getByRole("button", { name: /category/i }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Bank narration")).toContainText("REF000009");
  await dialog.getByLabel(/Always do this/).check();
  await expect(dialog).toContainText(/Matches \d+ existing transaction/);
  await dialog.getByRole("button", { name: /^Dining/ }).first().click();
  await expect(dialog).toBeHidden();

  await page.goto("/rules");
  await expect(page.getByRole("list", { name: "Rules" })).toContainText("Dining");
});

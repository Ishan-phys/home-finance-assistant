import { expect, test } from "@playwright/test";
import { completeSetup, createAccount, createPerson, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test("each account shows the badge of its bank or provider, and an icon for any other", async ({ page, request }) => {
  const person = await createPerson(request);
  const hdfc = await createAccount(request, person, { name: "HDFC Savings", type: "savings", institution: "HDFC Bank" });
  await createAccount(request, person, { name: "SBI Savings", type: "savings", institution: "SBI" });
  await createAccount(request, person, { name: "Axis Flipkart", type: "credit_card", institution: "Axis Bank" });
  await createAccount(request, person, { name: "Groww Funds", type: "mutual_fund", institution: "Groww" });
  await createAccount(request, person, { name: "Co-op FD", type: "fixed_deposit", institution: "Local Co-op Bank" });
  await completeSetup(request, person);

  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });
  const row = (name: string) => nav.getByRole("link", { name: new RegExp(name) }).getByTestId("institution-icon");
  await expect(row("HDFC Savings")).toHaveAttribute("data-institution", "hdfc");
  await expect(row("SBI Savings")).toHaveAttribute("data-institution", "sbi");
  await expect(row("Axis Flipkart")).toHaveAttribute("data-institution", "axis");
  await expect(row("Groww Funds")).toHaveAttribute("data-institution", "groww");
  await expect(row("Co-op FD")).toHaveAttribute("data-institution", "other"); // an icon for its kind

  // The badge is decoration: it never changes an account's name for a screen reader.
  await expect(nav.getByRole("link", { name: /^HDFC Savings/ })).toBeVisible();

  // The account's own page carries it beside the title.
  await page.goto(`/accounts/${hdfc}`);
  await expect(page.getByRole("heading", { name: "HDFC Savings" })).toBeVisible();
  await expect(page.getByRole("main").getByTestId("institution-icon").first()).toHaveAttribute("data-institution", "hdfc");
});

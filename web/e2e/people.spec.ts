import { expect, test } from "@playwright/test";
import { completeSetup, createAccount, createPerson, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test("deleting a person asks for their name, removes them, and leaves the other person", async ({ page, request }) => {
  const asha = await createPerson(request, "Asha Rao");
  await createAccount(request, asha, { name: "SBI Savings", type: "savings", institution: "SBI" });
  await completeSetup(request, asha);
  const pavani = await createPerson(request, "Pavani Priya");
  await createAccount(request, pavani, { name: "SBI Savings", type: "savings", institution: "SBI" });
  await completeSetup(request, pavani);

  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Main" });
  await nav.getByLabel("Viewing").selectOption({ label: "Pavani Priya" });
  await nav.getByRole("button", { name: "Delete person" }).click();

  const dialog = page.getByRole("dialog");
  const confirm = dialog.getByRole("button", { name: "Delete person" });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Type Pavani Priya to confirm").fill("Pavani Priya");
  await confirm.click();

  await expect(dialog).toBeHidden();
  await expect(nav.getByText("Asha Rao")).toBeVisible();
  const people = await (await request.get("/api/people")).json();
  expect(people.map((p: { name: string }) => p.name)).toEqual(["Asha Rao"]);
});

test("switching person on an account page returns to All accounts instead of an error", async ({ page, request }) => {
  const asha = await createPerson(request, "Asha Rao");
  const account = await createAccount(request, asha, { name: "SBI Savings", type: "savings", institution: "SBI" });
  await completeSetup(request, asha);
  const pavani = await createPerson(request, "Pavani Priya");
  await createAccount(request, pavani, { name: "SBI Savings", type: "savings", institution: "SBI" });
  await completeSetup(request, pavani);

  await page.goto(`/accounts/${account}`);
  const nav = page.getByRole("navigation", { name: "Main" });
  await nav.getByLabel("Viewing").selectOption({ label: "Pavani Priya" });

  await expect(page).toHaveURL(/\/accounts$/);
  await expect(page.getByText(/unknown account/i)).toHaveCount(0);
});

import { expect, test } from "@playwright/test";
import { OWNER } from "./global-setup";
import { completeSetup, createAccount, createPerson, resetDatabase } from "./helpers";

test.describe("signed out", () => {
  test.use({ storageState: { cookies: [], origins: [] } });
  test.beforeEach(() => resetDatabase());

  test("the app shows only the sign-in form, and the ledger refuses without a session", async ({
    page,
    request,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Sign in to AI CFO" })).toBeVisible();
    expect((await request.get("/api/people")).status()).toBe(401);
  });

  test("a wrong password is refused without saying which part was wrong", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Username").fill(OWNER.username);
    await page.getByLabel("Password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("That username or password is not right.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Sign in to AI CFO" })).toBeVisible();
  });

  test("the right password opens the app, and sign out returns to the form", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Username").fill(OWNER.username);
    await page.getByLabel("Password").fill(OWNER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Your money, in one honest ledger" })).toBeVisible();

    // The sidebar, and so Sign out, appears once a person has finished setup.
    const personId = await createPerson(page.request, "Asha Rao");
    await createAccount(page.request, personId, { name: "HDFC Savings", type: "savings", institution: "HDFC Bank" });
    await completeSetup(page.request, personId);
    await page.reload();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByRole("heading", { name: "Sign in to AI CFO" })).toBeVisible();
    expect((await page.request.get("/api/people")).status()).toBe(401);
  });
});

test.describe("sessions that end or fail", () => {
  test.beforeEach(async ({ request }) => {
    resetDatabase();
    const person = await createPerson(request, "Asha Rao");
    await createAccount(request, person, { name: "HDFC Savings", type: "savings", institution: "HDFC Bank" });
    await completeSetup(request, person);
  });

  test("a forged session cookie shows the form, not the ledger", async ({ page, context, baseURL }) => {
    await context.clearCookies();
    await context.addCookies([{ name: "cfo_session", value: "e30.e30", url: baseURL! }]);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Sign in to AI CFO" })).toBeVisible();
    await expect(page.getByText("HDFC Savings")).toHaveCount(0);
  });

  test("when the session ends mid-use, a refused request drops back to the form", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
    await page.route("**/api/people/**", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "NOT_SIGNED_IN", message: "Sign in to continue." } }),
      }),
    );
    // /auth/me still says signed in, but the ledger request is refused: the app must not sit on a
    // broken page, it must go back to the form.
    await page.reload();
    await expect(page.getByRole("heading", { name: "Sign in to AI CFO" })).toBeVisible();
  });

  test("a failed sign out says so and keeps the app open", async ({ page }) => {
    await page.goto("/");
    await page.route("**/api/auth/logout", (route) => route.fulfill({ status: 500, body: "" }));
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByText("Could not sign out")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  });
});

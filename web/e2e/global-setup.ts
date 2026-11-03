// Wait for the stack and warm it, so the first test does not pay for a cold start. Then sign in
// as the throwaway test owner once and keep the session, so every test starts signed in.
import fs from "node:fs";
import path from "node:path";
import { request } from "@playwright/test";

/** The test stack's owner (see docker-compose.e2e.yml). Synthetic values, never a real password. */
export const OWNER = { username: "owner", password: "e2e-owner-password" };
export const SESSION_FILE = path.join(__dirname, ".auth", "owner.json");

export default async function globalSetup() {
  const base = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";
  const deadline = Date.now() + 60_000;
  for (;;) {
    try {
      const health = await fetch(`${base}/api/health`);
      if (health.ok) break;
    } catch {
      /* not up yet */
    }
    if (Date.now() > deadline) throw new Error(`stack not reachable at ${base}; run: docker compose up -d`);
    await new Promise((r) => setTimeout(r, 1000));
  }
  await fetch(base);

  const api = await request.newContext({ baseURL: base });
  const res = await api.post("/api/auth/login", { data: OWNER });
  if (!res.ok()) throw new Error(`test sign-in failed (${res.status()}); check the e2e stack's OWNER_* settings`);
  fs.mkdirSync(path.dirname(SESSION_FILE), { recursive: true });
  await api.storageState({ path: SESSION_FILE });
  await api.dispose();
}

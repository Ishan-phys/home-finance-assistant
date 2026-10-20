// Wait for the stack and warm it, so the first test does not pay for a cold start.
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
  await fetch(`${base}/api/people`);
}

import { execSync } from "node:child_process";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "../..");
export const fixture = (name: string) => path.join(repoRoot, "fixtures", name);

/** Empty every table: no people, no ledgers, nothing. The schema stays. */
export function resetDatabase() {
  const sql =
    "TRUNCATE people, households, ledgers, ledger_settings, household_members, accounts, imports, " +
    "transactions, postings, assertions, import_hashes, valuations, dismissed_hashes, merchant_mappings, " +
    "redaction_terms, pseudonym_labels RESTART IDENTITY CASCADE;";
  execSync(`docker compose exec -T db psql -U cfo -d cfo -v ON_ERROR_STOP=1 -c "${sql}"`, {
    cwd: repoRoot,
    stdio: "pipe",
  });
}

export async function createPerson(
  request: import("@playwright/test").APIRequestContext,
  name = "Asha Rao",
): Promise<string> {
  const res = await request.post("/api/people", { data: { name } });
  if (!res.ok()) throw new Error(await res.text());
  return (await res.json()).id as string;
}

export async function createAccount(
  request: import("@playwright/test").APIRequestContext,
  personId: string,
  body: { name: string; type: string; institution: string },
): Promise<string> {
  const res = await request.post(`/api/people/${personId}/accounts`, { data: body });
  if (!res.ok()) throw new Error(await res.text());
  return (await res.json()).id as string;
}

export async function completeSetup(request: import("@playwright/test").APIRequestContext, personId: string) {
  const res = await request.post(`/api/people/${personId}/setup/complete`);
  if (!res.ok()) throw new Error(await res.text());
}

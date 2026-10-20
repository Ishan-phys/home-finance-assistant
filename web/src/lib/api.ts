// Types for the API, mirroring the reports (api/src/cfo/api/routes.py and cfo.ledger.reports).
// Every amount arrives as paise plus a preformatted string, so the browser never does money maths.

export interface Money {
  paise: number;
  formatted: string;
}

export interface Person {
  id: string;
  name: string;
  ledger_id: string;
}

export type AccountType =
  | "savings"
  | "current"
  | "cash"
  | "credit_card"
  | "loan"
  | "fixed_deposit"
  | "recurring_deposit"
  | "mutual_fund"
  | "stock"
  | "property"
  | "gold";

export type Group = "liquid" | "investments" | "fixed" | "other" | "owed";
export type Kind = "asset" | "liability" | "income" | "expense" | "equity";

export interface CatalogType {
  type: AccountType;
  label: string;
  manual: boolean;
  group: Group;
  kind: Kind;
}

export interface CatalogInstitution {
  name: string;
  accounts: { type: AccountType; binding: string | null; statements: boolean; hint: string }[];
}

export interface Catalog {
  types: CatalogType[];
  institutions: CatalogInstitution[];
}

export interface Account {
  id: string;
  path: string;
  name: string;
  kind: Kind;
  role: "real" | "category" | "system";
  type: AccountType | null;
  type_label: string | null;
  group: Group | null;
  institution: string | null;
  binding: string | null;
  manual: boolean;
  description: string | null;
  direction: "in" | "out" | null;
  heading: "regular" | "people" | "rewards";
  retired: boolean;
  balance?: Money;
  cost?: Money;
  market?: Money;
  unrealized?: Money;
}

export interface Category extends Account {
  parent_path: string | null;
  this_month: Money;
  used: number;
  default: boolean;
}

export interface Categories {
  out: Category[];
  in: Category[];
  own_move: { id: string; name: string; description: string };
}

export interface SheetGroup {
  group: Group;
  label: string;
  total: Money;
  accounts: Account[];
}

export interface BalanceSheet {
  as_of: string;
  net_worth: Money;
  groups: SheetGroup[];
}

export interface Side {
  id: string;
  name: string;
  kind: Kind | null;
  role: "real" | "category" | "system" | null;
}

export interface Posting {
  account_id: string;
  account: string;
  path: string;
  amount: Money;
  origin: "observed" | "inferred" | "owner" | "system";
}

export interface Txn {
  id: string;
  date: string;
  narration: string;
  payee: string;
  source: "import" | "manual" | "system";
  amount: Money;
  from: Side;
  to: Side;
  category: { id: string; name: string; path: string; uncategorized: boolean } | null;
  editable: boolean;
  postings: Posting[];
  change?: Money;
  running?: Money;
}

export interface Statement {
  import_id: string;
  file_name: string;
  period_start: string | null;
  period_end: string | null;
  rows_inserted: number;
  hashes_ignored: number;
  imported_at: string;
  closing_balance_paise: number | null;
  balance_as_of: string | null;
  amount_due_paise: number | null;
  due_date: string | null;
  assertion_ok: boolean;
  difference: Money | null;
}

export interface AccountPage {
  account: Account;
  register: Txn[];
  statements: Statement[];
  holdings?: { cost: Money; market: Money; unrealized: Money };
}

export interface InboxItem {
  kind: "uncategorized" | "unpaired" | "gap" | "card_due";
  amount: Money;
  date: string;
  account: { id: string; name: string } | null;
  transaction_id: string | null;
  text: string;
  action: "categorize" | "upload" | "pair";
}

export interface SafeToSpend {
  amount: Money;
  liquid: Money;
  kept_aside: Money;
  owed_on_cards: Money;
  available: Money;
  monthly_allowance: Money | null;
  allowance_remaining: Money | null;
  subtractions: { label: string; amount: Money }[];
}

export interface Overview {
  as_of: string;
  net_worth: { total: Money; change_since_last_month: Money };
  this_month: { month: string; earned: Money; spent: Money; saved: Money };
  safe_to_spend: SafeToSpend;
  inbox: { count: number; top: InboxItem[] };
}

export interface CategoryNode {
  path: string;
  name: string;
  account_id: string | null;
  amount: Money;
  depth: number;
  children: CategoryNode[];
}

export interface IncomeStatement {
  month: string;
  start: string;
  end: string;
  earned: Money;
  spent: Money;
  saved: Money;
  rewards: Money;
  people_in: Money;
  people_out: Money;
  revaluation: Money;
  check: {
    change_in_net_worth: Money;
    saved: Money;
    revaluation: Money;
    opening: Money;
    unrealized_change: Money;
    explained: Money;
    ok: boolean;
  };
  categories: { out: CategoryNode[]; in: CategoryNode[] };
}

export interface Leaks {
  month: string;
  complete: boolean;
  baseline_months: string[];
  reason: string | null;
  current: { category: string; payee: string; amount: Money; count: number }[];
  rows: { category: string; payee: string; current: Money; baseline_avg: Money; variance: Money; count: number }[];
}

export interface TreeNode {
  path: string;
  name: string;
  account_id: string | null;
  balance: Money;
  children: TreeNode[];
}

export interface AccountsTree {
  as_of: string;
  kinds: { kind: Kind; label: string; total: Money; nodes: TreeNode[] }[];
}

export interface Settings {
  min_cash_buffer: Money;
  monthly_allowance: Money | null;
  setup_completed_at: string | null;
}

export interface SetupState {
  completed: boolean;
  accounts: number;
}

export interface UploadResult {
  import_id: string;
  rows_inserted: number;
  hashes_ignored: number;
  pairs_merged: number;
  uncategorized: number;
  gaps: number;
  warnings: string[];
  redaction: Record<string, number>;
}

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public correlationId: string | null,
    public hint: string | null = null,
    public detail: string | null = null,
  ) {
    super(message);
  }
}

// Everything except people and the sample belongs to one person's ledger, so the client prefixes
// those paths with the active person. The dashboard sets it before its children render.
let currentPerson: string | null = null;

export function setCurrentPerson(id: string | null) {
  currentPerson = id;
}

export function personPath(path: string): string {
  if (path.startsWith("/people") || path.startsWith("/sample") || path.startsWith("/health") || path.startsWith("/catalog")) return path;
  if (!currentPerson) throw new Error("no person is selected");
  return `/people/${currentPerson}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${personPath(path)}`, { cache: "no-store", ...init });
  if (!res.ok) {
    let body: { error?: { code: string; message: string; hint?: string | null; detail?: string | null; correlation_id: string } } = {};
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(
      body.error?.code ?? "ERROR",
      body.error?.message ?? res.statusText,
      body.error?.correlation_id ?? null,
      body.error?.hint ?? null,
      body.error?.detail ?? null,
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, json("POST", body)),
  put: <T>(path: string, body?: unknown) => request<T>(path, json("PUT", body)),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, json("PATCH", body)),
  upload: <T>(path: string, file: File, password?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (password) form.append("password", password);
    return request<T>(path, { method: "POST", body: form });
  },
};

/** What to show the owner: the plain-language message and what to do about it. The reference id
 * is only worth quoting for faults on our side. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const hint = e.hint ? ` ${e.hint}` : "";
    const ref = e.code === "INTERNAL" && e.correlationId ? ` (reference ${e.correlationId.slice(0, 8)})` : "";
    return `${e.message}${hint}${ref}`;
  }
  return e instanceof Error ? e.message : String(e);
}

/** Rupees typed by the owner ("1,00,000.50") to integer paise, or null when invalid. */
export function toPaise(text: string): number | null {
  const cleaned = text.replace(/[,₹\s]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [whole, frac = ""] = cleaned.split(".");
  return Number(whole) * 100 + Number(frac.padEnd(2, "0"));
}

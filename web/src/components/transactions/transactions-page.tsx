"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { EmptyState, ErrorNote, Loading, NativeSelect, PageHeader } from "@/components/common/shared";
import { Input } from "@/components/ui/input";
import type { BalanceSheet, Categories, Txn } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useApi } from "@/lib/use-api";
import { TxnTable } from "./txn-table";

export function TransactionsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const { version } = usePerson();
  const [q, setQ] = useState(params.get("q") ?? "");
  const search = useRef<HTMLInputElement>(null);
  const account = params.get("account_id") ?? "";
  const category = params.get("category_id") ?? "";
  const month = params.get("month") ?? "";

  const query = new URLSearchParams();
  if (account) query.set("account_id", account);
  if (category) query.set("category_id", category);
  if (month) query.set("month", month);
  if (q.trim()) query.set("q", q.trim());
  const rows = useApi<Txn[]>(`/transactions?${query}`, version);
  const sheet = useApi<BalanceSheet>("/reports/balance-sheet", version);
  const cats = useApi<Categories>("/categories", version);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`/transactions?${next}`);
  }

  const accounts = (sheet.data?.groups ?? []).flatMap((g) => g.accounts).filter((a) => a.role === "real");
  const categories = [...(cats.data?.out ?? []), ...(cats.data?.in ?? [])];

  return (
    <div>
      <PageHeader title="Transactions" subtitle="Everything that happened, newest first. Open a row to see its bookkeeping." />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input ref={search} className="w-64" placeholder="Search (press /)" aria-label="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        <NativeSelect aria-label="Account" value={account} onChange={(e) => setFilter("account_id", e.target.value)}>
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </NativeSelect>
        <NativeSelect aria-label="Category" value={category} onChange={(e) => setFilter("category_id", e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </NativeSelect>
        {month ? (
          <button type="button" className="rounded-lg border px-2 text-sm text-muted-foreground hover:bg-muted" onClick={() => setFilter("month", "")}>
            {month} ✕
          </button>
        ) : null}
      </div>
      {rows.data ? (
        rows.data.length ? <TxnTable rows={rows.data} /> : <EmptyState title="No transactions match" />
      ) : rows.error ? (
        <ErrorNote message={rows.error} />
      ) : (
        <Loading what="transactions" />
      )}
    </div>
  );
}

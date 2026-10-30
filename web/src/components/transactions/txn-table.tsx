"use client";

import { ArrowRight, ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";
import { Amount, shortDate } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import { api, type Txn } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction } from "@/lib/use-api";
import { CategoryPicker } from "./category-picker";

const ORIGIN: Record<string, string> = {
  observed: "from the statement",
  inferred: "categorized",
  owner: "set by you",
  system: "opening balance",
};

/** Transactions as "From → To". A row opens to show its bookkeeping: every posting, which
 * account it touched and by how much, and where each side came from. */
export function TxnTable({ rows, running = false }: { rows: Txn[]; running?: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  const { refresh } = usePerson();
  const ignore = useAction(refresh);

  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
          <tr>
            <th className="w-8" />
            <th className="px-2 py-2 font-medium">Date</th>
            <th className="px-2 py-2 font-medium">Description</th>
            <th className="px-2 py-2 font-medium">From → To</th>
            <th className="px-2 py-2 font-medium">Category</th>
            <th className="px-2 py-2 text-right font-medium">Amount</th>
            {running ? <th className="px-3 py-2 text-right font-medium">Balance</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => {
            const expanded = open === t.id;
            const shown = t.change ?? t.amount;
            return (
              <Fragment key={t.id}>
                <tr className="border-t align-top hover:bg-muted/20">
                  <td className="py-2 pl-2">
                    <button
                      type="button"
                      aria-label={expanded ? "Hide bookkeeping" : "Show bookkeeping"}
                      aria-expanded={expanded}
                      onClick={() => setOpen(expanded ? null : t.id)}
                      className="rounded p-0.5 text-muted-foreground hover:bg-muted"
                    >
                      {expanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    </button>
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-muted-foreground">{shortDate(t.date)}</td>
                  <td className="max-w-[18rem] px-2 py-2">
                    <div className="truncate font-medium">{t.payee}</div>
                    {(t.original ?? t.narration) !== t.payee ? (
                      <div className="truncate text-xs text-muted-foreground" title={t.original ?? t.narration}>
                        {t.original ?? t.narration}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap items-center gap-1">
                      <span>{t.from.name}</span>
                      <ArrowRight className="size-3.5 text-muted-foreground" aria-label="to" />
                      <span>{t.to.name}</span>
                    </div>
                  </td>
                  <td className="px-2 py-1.5">
                    {t.editable ? (
                      <CategoryPicker
                        txnId={t.id}
                        narration={t.original ?? t.narration}
                        current={
                          t.category && !t.category.uncategorized
                            ? t.category.name
                            : t.postings.some((p) => p.path === "Assets:InTransit")
                              ? "Own account: waiting"
                              : null
                        }
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground">{t.source === "system" ? "Opening" : "Transfer"}</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-right">
                    <Amount value={shown} />
                  </td>
                  {running ? (
                    <td className="whitespace-nowrap px-3 py-2 text-right text-muted-foreground">
                      {t.running ? <Amount value={t.running} /> : null}
                    </td>
                  ) : null}
                </tr>
                {expanded ? (
                  <tr className="bg-muted/20">
                    <td />
                    <td colSpan={running ? 6 : 5} className="px-2 pb-3">
                      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        {t.original ? "Bank narration" : "Narration (personal details hidden)"}
                      </p>
                      <p className="mb-3 break-all font-mono text-xs">{t.original ?? t.narration}</p>
                      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Bookkeeping</p>
                      <table className="text-xs">
                        <tbody>
                          {t.postings.map((p, i) => (
                            <tr key={i}>
                              <td className="pr-4 font-mono">{p.path}</td>
                              <td className="pr-4 text-right tabular-nums">{p.amount.formatted}</td>
                              <td className="text-muted-foreground">{ORIGIN[p.origin]}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p className="mt-1 text-xs text-muted-foreground">The postings add up to zero: money left one place and arrived in another.</p>
                      {t.editable && t.source === "import" ? (
                        <Button
                          variant="ghost"
                          size="xs"
                          className="mt-2"
                          disabled={ignore.busy}
                          onClick={() => void ignore.run(() => api.post(`/transactions/${t.id}/ignore`))}
                        >
                          Ignore this row
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

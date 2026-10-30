"use client";

import Link from "next/link";
import { useState } from "react";
import { Amount, EmptyState, ErrorNote, Loading, shortDate } from "@/components/common/shared";
import { CategoryPicker } from "@/components/transactions/category-picker";
import { Button } from "@/components/ui/button";
import { api, type InboxItem } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction, useApi } from "@/lib/use-api";

/** One list of everything that needs the owner, each with its fix next to it. */
export function InboxList({ limit }: { limit?: number }) {
  const { version, refresh } = usePerson();
  const items = useApi<InboxItem[]>("/inbox", version);
  const retry = useAction(refresh);
  const [note, setNote] = useState<string | null>(null);
  if (!items.data) return items.error ? <ErrorNote message={items.error} /> : <Loading what="the inbox" />;
  if (!items.data.length) return <EmptyState title="All caught up.">Nothing needs your attention.</EmptyState>;
  const shown = limit ? items.data.slice(0, limit) : items.data;
  const waiting = items.data.filter((i) => i.kind === "uncategorized").length;
  return (
    <div className="space-y-3">
      {waiting ? (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-muted/30 px-3 py-2.5">
          <p className="min-w-0 flex-1 text-sm">
            {waiting} transaction{waiting === 1 ? " is" : "s are"} waiting for a category. If a statement came in uncategorized, try again.
            {note ? <span className="block text-xs text-muted-foreground">{note}</span> : null}
          </p>
          <Button
            variant="outline"
            size="sm"
            disabled={retry.busy}
            onClick={async () => {
              const r = await retry.run(() => api.post<{ rows_updated: number; warnings: string[] }>("/categorization/retry"));
              if (r) setNote([`${r.rows_updated} categorized.`, ...r.warnings].join(" "));
            }}
          >
            Retry categorization
          </Button>
        </div>
      ) : null}
      <ErrorNote message={retry.error} />
    <ul aria-label="Inbox" className="divide-y rounded-xl border">
      {shown.map((item, i) => (
        <li key={`${item.kind}-${item.transaction_id ?? item.account?.id}-${i}`} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
          <div className="min-w-0 flex-1">
            <p className="text-sm">{item.text}</p>
            {item.original ? <p className="break-all font-mono text-xs text-muted-foreground">{item.original}</p> : null}
            <p className="text-xs text-muted-foreground">
              {shortDate(item.date)} · <Amount value={item.amount} />
            </p>
          </div>
          {item.action === "categorize" && item.transaction_id ? <CategoryPicker txnId={item.transaction_id} current={null} narration={item.original} /> : null}
          {item.action === "upload" && item.account ? (
            <Button variant="outline" size="sm" render={<Link href={`/accounts/${item.account.id}?upload=1`} />}>
              Upload
            </Button>
          ) : null}
          {item.action === "pair" && item.account ? (
            <Button variant="ghost" size="sm" render={<Link href={`/accounts/${item.account.id}`} />}>
              Open account
            </Button>
          ) : null}
        </li>
      ))}
    </ul>
    </div>
  );
}

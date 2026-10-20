"use client";

import Link from "next/link";
import { Amount, EmptyState, ErrorNote, Loading, shortDate } from "@/components/common/shared";
import { CategoryPicker } from "@/components/transactions/category-picker";
import { Button } from "@/components/ui/button";
import type { InboxItem } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useApi } from "@/lib/use-api";

/** One list of everything that needs the owner, each with its fix next to it. */
export function InboxList({ limit }: { limit?: number }) {
  const { version } = usePerson();
  const items = useApi<InboxItem[]>("/inbox", version);
  if (!items.data) return items.error ? <ErrorNote message={items.error} /> : <Loading what="the inbox" />;
  if (!items.data.length) return <EmptyState title="All caught up.">Nothing needs your attention.</EmptyState>;
  const shown = limit ? items.data.slice(0, limit) : items.data;
  return (
    <ul aria-label="Inbox" className="divide-y rounded-xl border">
      {shown.map((item, i) => (
        <li key={`${item.kind}-${item.transaction_id ?? item.account?.id}-${i}`} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
          <div className="min-w-0 flex-1">
            <p className="text-sm">{item.text}</p>
            <p className="text-xs text-muted-foreground">
              {shortDate(item.date)} · <Amount value={item.amount} />
            </p>
          </div>
          {item.action === "categorize" && item.transaction_id ? <CategoryPicker txnId={item.transaction_id} current={null} /> : null}
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
  );
}

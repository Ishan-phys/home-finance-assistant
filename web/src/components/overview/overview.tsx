"use client";

import Link from "next/link";
import { Amount, ErrorNote, Loading, PageHeader } from "@/components/common/shared";
import { Panel } from "@/components/common/panel";
import { InboxList } from "@/components/inbox/inbox-list";
import { Button } from "@/components/ui/button";
import type { BalanceSheet, Overview } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useApi } from "@/lib/use-api";

function monthName(month: string): string {
  return new Date(`${month}-01T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

/** Four things only: what I am worth, this month, what I can spend, and what needs me. */
export function OverviewPage() {
  const { version } = usePerson();
  const view = useApi<Overview>("/reports/overview", version);
  const sheet = useApi<BalanceSheet>("/reports/balance-sheet", version);
  const firstFeed = (sheet.data?.groups ?? []).flatMap((g) => g.accounts).find((a) => a.role === "real" && a.binding);

  if (!view.data) return view.error ? <ErrorNote message={view.error} /> : <Loading what="your overview" />;
  const { net_worth, this_month, safe_to_spend: sts, inbox } = view.data;
  const change = net_worth.change_since_last_month;

  return (
    <div>
      <PageHeader
        title="Overview"
        action={
          firstFeed ? (
            <Button render={<Link href={`/accounts/${firstFeed.id}?upload=1`} />}>Upload statement</Button>
          ) : null
        }
      />
      <div className="grid gap-4 md:grid-cols-3">
        <Panel title="Net worth" action={<Link href="/accounts" className="text-xs text-muted-foreground hover:underline">Breakdown</Link>}>
          <p className="text-3xl font-semibold tracking-tight tabular-nums">{net_worth.total.formatted}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {change.paise === 0 ? "No change" : `${change.paise > 0 ? "Up" : "Down"} ${change.formatted.replace("-", "")}`} since last month
          </p>
          <p className="mt-2 text-xs text-muted-foreground">What you own, less what you owe on cards and loans.</p>
        </Panel>

        <Panel title="This month" action={<Link href="/spending" className="text-xs text-muted-foreground hover:underline">{monthName(this_month.month)}</Link>}>
          <dl className="space-y-1.5 text-sm">
            {(
              [
                ["Earned", this_month.earned],
                ["Spent", this_month.spent],
                ["Saved", this_month.saved],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="flex items-baseline justify-between">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className={label === "Saved" ? "text-lg font-semibold" : ""}>
                  <Amount value={value} />
                </dd>
              </div>
            ))}
          </dl>
        </Panel>

        <Panel title="Safe to spend">
          <p className="text-3xl font-semibold tracking-tight tabular-nums">{sts.amount.formatted}</p>
          <details className="mt-2 text-sm">
            <summary className="cursor-pointer text-xs text-muted-foreground">How is this worked out?</summary>
            <dl className="mt-2 space-y-1">
              <div className="flex justify-between">
                <dt>Cash and savings</dt>
                <dd><Amount value={sts.liquid} /></dd>
              </div>
              {sts.subtractions.map((s) => (
                <div key={s.label} className="flex justify-between text-muted-foreground">
                  <dt>− {s.label}</dt>
                  <dd><Amount value={s.amount} /></dd>
                </div>
              ))}
              {sts.allowance_remaining ? (
                <div className="flex justify-between text-muted-foreground">
                  <dt>Capped at what is left of the monthly allowance</dt>
                  <dd><Amount value={sts.allowance_remaining} /></dd>
                </div>
              ) : null}
            </dl>
            <p className="mt-2 text-xs text-muted-foreground">
              Investments, deposits and property are never counted. Change the base amount in{" "}
              <Link href="/settings" className="underline">Settings</Link>.
            </p>
          </details>
        </Panel>
      </div>

      <Panel
        title="Inbox"
        className="mt-4"
        action={
          inbox.count > 3 ? (
            <Link href="/inbox" className="text-xs text-muted-foreground hover:underline">See all {inbox.count}</Link>
          ) : null
        }
      >
        <InboxList limit={3} />
      </Panel>
    </div>
  );
}

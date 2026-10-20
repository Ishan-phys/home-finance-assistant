"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Amount, EmptyState, ErrorNote, Loading, PageHeader } from "@/components/common/shared";
import { Panel } from "@/components/common/panel";
import { Button } from "@/components/ui/button";
import type { CategoryNode, IncomeStatement, Leaks } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useApi } from "@/lib/use-api";

function shift(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthName(month: string): string {
  return new Date(`${month}-01T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

function Tree({ nodes, max, month }: { nodes: CategoryNode[]; max: number; month: string }) {
  return (
    <ul className="space-y-1">
      {nodes.map((n) => (
        <li key={n.path}>
          <div className="flex items-center gap-3 text-sm">
            <div className="w-28 shrink-0 truncate sm:w-36" style={{ paddingLeft: `${(n.depth - 1) * 0.75}rem` }}>
              {n.account_id ? (
                <Link href={`/transactions?category_id=${n.account_id}&month=${month}`} className="hover:underline">
                  {n.name}
                </Link>
              ) : (
                <span className="font-medium">{n.name}</span>
              )}
            </div>
            <div className="h-2 min-w-0 flex-1 rounded-full bg-muted" aria-hidden>
              <div className="h-2 rounded-full bg-primary/70" style={{ width: `${max ? Math.max(2, (100 * Math.abs(n.amount.paise)) / max) : 0}%` }} />
            </div>
            <Amount value={n.amount} className="shrink-0 text-right" />
          </div>
          {n.children.length ? <div className="mt-1"><Tree nodes={n.children} max={max} month={month} /></div> : null}
        </li>
      ))}
    </ul>
  );
}

export function SpendingPage() {
  const params = useSearchParams();
  const router = useRouter();
  const { version } = usePerson();
  const asked = params.get("month");
  const stmt = useApi<IncomeStatement>(`/reports/income-statement${asked ? `?month=${asked}` : ""}`, version);
  const month = stmt.data?.month ?? asked;
  const leaks = useApi<Leaks>(month ? `/reports/leaks?month=${month}` : null, version);

  if (!stmt.data || !month) return stmt.error ? <ErrorNote message={stmt.error} /> : <Loading what="spending" />;
  const s = stmt.data;
  const out = s.categories.out.filter((n) => !n.path.startsWith("Expenses:People"));
  const max = Math.max(0, ...out.map((n) => Math.abs(n.amount.paise)));
  const c = s.check;
  const extras = [
    c.revaluation.paise ? `revaluation ${c.revaluation.formatted}` : null,
    c.opening.paise ? `opening balances ${c.opening.formatted}` : null,
    c.unrealized_change.paise ? `investment value ${c.unrealized_change.formatted}` : null,
  ].filter(Boolean);

  return (
    <div>
      <PageHeader
        title="Spending"
        subtitle="Where your money came from and where it went."
        action={
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon-sm" aria-label="Previous month" onClick={() => router.push(`/spending?month=${shift(month, -1)}`)}>
              <ChevronLeft />
            </Button>
            <span className="min-w-32 text-center text-sm font-medium">{monthName(month)}</span>
            <Button variant="ghost" size="icon-sm" aria-label="Next month" onClick={() => router.push(`/spending?month=${shift(month, 1)}`)}>
              <ChevronRight />
            </Button>
          </div>
        }
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <Panel title="Earned"><p className="text-2xl font-semibold tabular-nums">{s.earned.formatted}</p></Panel>
        <Panel title="Spent"><p className="text-2xl font-semibold tabular-nums">{s.spent.formatted}</p></Panel>
        <Panel title="Saved"><p className="text-2xl font-semibold tabular-nums">{s.saved.formatted}</p></Panel>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Net worth changed by {c.change_in_net_worth.formatted}: saved {c.saved.formatted}
        {extras.length ? ` + ${extras.join(" + ")}` : ""} {c.ok ? "✓" : "✗ these do not add up; check the Inbox"}
      </p>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Panel title="Where it went" className="lg:col-span-2">
          {out.length ? <Tree nodes={out} max={max} month={month} /> : <EmptyState title="No spending this month" />}
          {s.people_out.paise || s.people_in.paise || s.rewards.paise ? (
            <dl className="mt-4 space-y-1 border-t pt-3 text-sm text-muted-foreground">
              {s.people_out.paise ? <div className="flex justify-between"><dt>Sent to people</dt><dd><Amount value={s.people_out} /></dd></div> : null}
              {s.people_in.paise ? <div className="flex justify-between"><dt>Received from people</dt><dd><Amount value={s.people_in} /></dd></div> : null}
              {s.rewards.paise ? <div className="flex justify-between"><dt>Rewards and cashback</dt><dd><Amount value={s.rewards} /></dd></div> : null}
            </dl>
          ) : null}
        </Panel>
        <Panel title="Where it came from">
          {s.categories.in.length ? <Tree nodes={s.categories.in} max={Math.max(0, ...s.categories.in.map((n) => Math.abs(n.amount.paise)))} month={month} /> : <EmptyState title="No income this month" />}
        </Panel>
      </div>

      <Panel title="Spending that grew" className="mt-4">
        {leaks.data?.rows.length ? (
          <ul className="space-y-1 text-sm">
            {leaks.data.rows.slice(0, 5).map((r) => (
              <li key={`${r.category}-${r.payee}`} className="flex justify-between gap-3">
                <span className="truncate">{r.payee} <span className="text-muted-foreground">· {r.category}</span></span>
                <span className="shrink-0 tabular-nums">+{r.variance.formatted} <span className="text-muted-foreground">vs usual {r.baseline_avg.formatted}</span></span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            {leaks.data?.reason === "PARTIAL_MONTH"
              ? "Shown once the month is over and its statements are in."
              : leaks.data?.reason === "NO_BASELINE"
                ? "Needs earlier months to compare with."
                : "Nothing grew compared with the usual."}
          </p>
        )}
      </Panel>
    </div>
  );
}

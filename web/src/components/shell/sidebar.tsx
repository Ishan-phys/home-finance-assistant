"use client";

import { ArrowLeftRight, BookOpen, Inbox, LayoutDashboard, PieChart, Plus, Settings, Sparkles, Tags } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Amount } from "@/components/common/shared";
import type { BalanceSheet, InboxItem } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";
import { PersonSwitcher } from "./people";

function NavLink({
  href,
  icon,
  children,
  badge,
  exact = false,
}: {
  href: string;
  icon: ReactNode;
  children: ReactNode;
  badge?: number;
  exact?: boolean;
}) {
  const path = usePathname();
  const active = href === "/" || exact ? path === href : path === href || path.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
        active ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
      )}
    >
      <span className="[&_svg]:size-4">{icon}</span>
      <span className="flex-1">{children}</span>
      {badge ? (
        <span aria-label={`${badge} to do`} className="rounded-full bg-primary px-1.5 text-[11px] font-medium text-primary-foreground">
          {badge}
        </span>
      ) : null}
    </Link>
  );
}

export function Sidebar({ onAsk }: { onAsk: () => void }) {
  const { version, people, person, select } = usePerson();
  const sheet = useApi<BalanceSheet>("/reports/balance-sheet", version);
  const inbox = useApi<InboxItem[]>("/inbox", version);
  const path = usePathname();

  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-4 overflow-y-auto px-3 py-4">
      <div className="px-2.5">
        <p className="text-sm font-semibold">AI CFO</p>
        {people && person ? <PersonSwitcher people={people} current={person.id} onSelect={select} /> : null}
      </div>

      <div className="space-y-0.5">
        <NavLink href="/" icon={<LayoutDashboard />}>Overview</NavLink>
        <NavLink href="/inbox" icon={<Inbox />} badge={inbox.data?.length}>Inbox</NavLink>
        <NavLink href="/spending" icon={<PieChart />}>Spending</NavLink>
        <NavLink href="/transactions" icon={<ArrowLeftRight />}>Transactions</NavLink>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between px-2.5">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Accounts</span>
          <Link href="/setup?step=accounts" aria-label="Add account" className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <Plus className="size-4" />
          </Link>
        </div>
        {(sheet.data?.groups ?? [])
          .filter((g) => g.accounts.some((a) => a.role === "real"))
          .map((g) => (
            <div key={g.group}>
              <div className="flex items-baseline justify-between px-2.5 text-xs text-muted-foreground">
                <span>{g.label}</span>
                <Amount value={g.total} />
              </div>
              <ul className="mt-0.5">
                {g.accounts
                  .filter((a) => a.role === "real")
                  .map((a) => (
                    <li key={a.id}>
                      <Link
                        href={`/accounts/${a.id}`}
                        aria-current={path === `/accounts/${a.id}` ? "page" : undefined}
                        className={cn(
                          "flex items-baseline justify-between gap-2 rounded-lg px-2.5 py-1 text-sm hover:bg-muted/60",
                          path === `/accounts/${a.id}` && "bg-muted font-medium",
                        )}
                      >
                        <span className="truncate">{a.name}</span>
                        {a.balance ? <Amount value={a.balance} className="text-xs text-muted-foreground" /> : null}
                      </Link>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
      </div>

      <div className="mt-auto space-y-0.5 border-t pt-3">
        <NavLink href="/accounts" icon={<BookOpen />} exact>
          All accounts
        </NavLink>
        <NavLink href="/categories" icon={<Tags />}>Categories</NavLink>
        <NavLink href="/settings" icon={<Settings />}>Settings</NavLink>
        <button
          type="button"
          onClick={onAsk}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-muted/60 hover:text-foreground"
        >
          <Sparkles className="size-4" />
          Ask
        </button>
      </div>
    </nav>
  );
}

"use client";

import type { ReactNode } from "react";
import type { Money } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Amount({ value, className }: { value: Money; className?: string }) {
  return <span className={cn("tabular-nums", className)}>{value.formatted}</span>;
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "muted";
}) {
  return (
    <div className="min-w-0">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("text-xl font-semibold tabular-nums", tone === "muted" && "text-muted-foreground")}>
        {value}
      </div>
      {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {message}
    </p>
  );
}

export function Warnings({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <ul className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-900 dark:text-amber-200">
      {items.map((w, i) => (
        <li key={i}>{w}</li>
      ))}
    </ul>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="text-sm text-muted-foreground">Loading {what}…</p>;
}

export function NativeSelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        props.className,
      )}
    />
  );
}

export function shortDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </header>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children ? <div className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{children}</div> : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

/** A signed amount where colour is never the only signal: money out carries a minus sign. */
export function Signed({ value, className }: { value: Money; className?: string }) {
  return (
    <span className={cn("tabular-nums", value.paise < 0 ? "text-foreground" : "text-emerald-700 dark:text-emerald-400", className)}>
      {value.formatted}
    </span>
  );
}

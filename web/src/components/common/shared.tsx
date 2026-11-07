"use client";

import { AlertCircle, Info } from "lucide-react";
import { useSyncExternalStore, type ReactNode } from "react";
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
      <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn("font-figure text-2xl font-medium", tone === "muted" && "text-muted-foreground")}>
        {value}
      </div>
      {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{message}</span>
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

/** A shimmering placeholder shaped like the page, so nothing jumps when data arrives. The words
 * stay for screen readers and tests; the shimmer is decoration. */
export function Loading({ what, page = false }: { what: string; page?: boolean }) {
  if (!page) {
    return (
      <div role="status" aria-busy="true">
        <p className="sr-only">Loading {what}…</p>
        <div aria-hidden className="skeleton h-5 w-40" />
      </div>
    );
  }
  return (
    <div role="status" aria-busy="true" aria-live="polite">
      <p className="sr-only">Loading {what}…</p>
      <div aria-hidden className="space-y-4">
        <div className="skeleton h-8 w-48" />
        <div className="grid gap-4 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-32" />
          ))}
        </div>
        <div className="skeleton h-40" />
      </div>
    </div>
  );
}

export function NativeSelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "h-9 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors hover:border-ring/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
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

export interface PageAbout {
  /** A stable name for remembering whether the reader closed it, e.g. "spending". */
  id: string;
  /** One or two sentences: what this page is for. */
  summary?: ReactNode;
  /** Short, concrete things the reader can do here or should know. */
  points?: ReactNode[];
}

const GUIDE_EVENT = "cfo-guide";

function subscribeGuides(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(GUIDE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(GUIDE_EVENT, onChange);
  };
}

/** A collapsible note that says what a page is for. It starts open and stays closed once the
 * reader closes it; the choice lives in localStorage, read before the first paint. */
export function PageGuide({
  about,
  title = "About this page",
  className,
}: {
  about: PageAbout;
  title?: string;
  className?: string;
}) {
  const key = `cfo-guide:${about.id}`;
  const closed = useSyncExternalStore(
    subscribeGuides,
    () => window.localStorage.getItem(key) === "closed",
    () => false,
  );
  return (
    <details open={!closed} className={cn("rounded-xl border border-accent-foreground/15 bg-accent/60 px-3.5 py-2.5 text-sm", className)}>
      <summary
        className="flex cursor-pointer list-none items-center gap-2 font-medium text-accent-foreground"
        onClick={(e) => {
          // The open state is ours, not the browser's: only a click changes it.
          e.preventDefault();
          window.localStorage.setItem(key, closed ? "open" : "closed");
          window.dispatchEvent(new Event(GUIDE_EVENT));
        }}
      >
        <Info className="size-4 shrink-0" aria-hidden />
        {title}
      </summary>
      <div className="mt-2 space-y-2 text-muted-foreground">
        {about.summary ? <p>{about.summary}</p> : null}
        {about.points?.length ? (
          <ul className="list-disc space-y-1 pl-5">
            {about.points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </details>
  );
}

export function PageHeader({
  title,
  subtitle,
  action,
  about,
}: {
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  about?: PageAbout;
}) {
  return (
    <>
      <header className={cn("flex flex-wrap items-start justify-between gap-3", about ? "mb-4" : "mb-8")}>
        <div className="min-w-0">
          <h1 className="text-3xl font-medium tracking-tight md:text-4xl">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
        </div>
        {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
      </header>
      {about ? <PageGuide about={about} className="mb-6" /> : null}
    </>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed bg-card/50 px-6 py-12 text-center">
      <p className="font-heading text-lg font-medium">{title}</p>
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

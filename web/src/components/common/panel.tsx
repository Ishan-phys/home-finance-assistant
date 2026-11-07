import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** A titled block on a page. It is a landmark region, named by its title. */
export function Panel({
  title,
  children,
  action,
  className,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section aria-label={title} className={cn("surface rounded-2xl border bg-card p-5", className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

"use client";

import type { ReactNode } from "react";
import { InlineText } from "@/components/common/inline-text";
import { api, type Category } from "@/lib/api";

/** Categories with their descriptions, both editable in place. `actions` adds per-row controls. */
export function CategoryList({
  title,
  items,
  onChanged,
  actions,
}: {
  title: string;
  items: Category[];
  onChanged: () => void;
  actions?: (c: Category) => ReactNode;
}) {
  const live = items.filter((c) => !c.retired);
  return (
    <section aria-label={title} className="space-y-2">
      <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>
      <ul className="divide-y rounded-xl border">
        {live.map((c) => (
          <li key={c.id} className="flex items-start gap-3 px-3 py-2">
            <div className="min-w-0 flex-1">
              {c.parent_path ? (
                <span className="text-xs text-muted-foreground">{c.parent_path.split(":").slice(1).join(" › ")} ›</span>
              ) : null}
              <InlineText
                label={`name of ${c.name}`}
                value={c.name}
                className="text-sm font-medium"
                onSave={async (name) => {
                  await api.patch(`/categories/${c.id}`, { name });
                  onChanged();
                }}
              />
              <InlineText
                label={`description of ${c.name}`}
                value={c.description ?? ""}
                placeholder="Add a line on what this is for"
                className="text-xs text-muted-foreground"
                onSave={async (description) => {
                  await api.patch(`/categories/${c.id}`, { description });
                  onChanged();
                }}
              />
              <InlineText
                label={`keywords of ${c.name}`}
                value={c.keywords ?? ""}
                placeholder="Add a few words that mark this category, e.g. haircut, spa"
                className="text-xs italic text-muted-foreground"
                onSave={async (keywords) => {
                  await api.patch(`/categories/${c.id}`, { keywords });
                  onChanged();
                }}
              />
            </div>
            {actions ? <div className="shrink-0">{actions(c)}</div> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

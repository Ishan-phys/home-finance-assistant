"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/** Text the owner edits in place: click, type, and it saves on Enter or when focus leaves.
 * Escape puts the old value back. */
export function InlineText({
  value,
  label,
  onSave,
  className,
  placeholder,
}: {
  value: string;
  label: string;
  onSave: (next: string) => Promise<unknown> | void;
  className?: string;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const editing = draft !== null;

  async function commit() {
    if (draft === null) return;
    const next = draft.trim();
    setDraft(null);
    if (next && next !== value) await onSave(next);
  }

  if (!editing) {
    return (
      <button
        type="button"
        aria-label={`Edit ${label}`}
        onClick={() => setDraft(value)}
        className={cn("w-full rounded px-1 -mx-1 text-left hover:bg-muted/60", !value && "text-muted-foreground", className)}
      >
        {value || placeholder || "Add"}
      </button>
    );
  }
  return (
    <input
      aria-label={label}
      autoFocus
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => void commit()}
      onKeyDown={(e) => {
        if (e.key === "Enter") void commit();
        if (e.key === "Escape") setDraft(null);
      }}
      className={cn("w-full rounded border border-input bg-transparent px-1 -mx-1 outline-none focus-visible:ring-2 focus-visible:ring-ring/50", className)}
    />
  );
}

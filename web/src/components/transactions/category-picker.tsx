"use client";

import { useState } from "react";
import { ErrorNote } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, type Categories } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction, useApi } from "@/lib/use-api";

interface Choice {
  id: string;
  name: string;
  description: string | null;
}

/** Pick the category for a transaction. Every category shows what it is for, so the choice
 * means the same thing to the owner and to the categorizer. The choice is remembered for the
 * same description in later statements. */
export function CategoryPicker({ txnId, current }: { txnId: string; current: string | null }) {
  const { version, refresh } = usePerson();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const cats = useApi<Categories>(open ? "/categories" : null, version);
  const { run, error, busy } = useAction(refresh);

  const q = query.trim().toLowerCase();
  const match = (c: Choice) => !q || c.name.toLowerCase().includes(q) || (c.description ?? "").toLowerCase().includes(q);
  const sections: { title: string; items: Choice[] }[] = cats.data
    ? [
        { title: "Money out", items: cats.data.out.filter((c) => !c.retired) },
        { title: "Money in", items: cats.data.in.filter((c) => !c.retired) },
        { title: "Between your accounts", items: cats.data.own_move?.id ? [cats.data.own_move] : [] },
      ]
    : [];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant={current ? "ghost" : "outline"} size="sm" aria-label={current ? `Change category ${current}` : "Choose category"}>
            {current ?? "Choose category"}
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Choose a category</DialogTitle>
        </DialogHeader>
        <Input autoFocus placeholder="Search categories" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="max-h-[50vh] space-y-4 overflow-y-auto">
          {sections.map((section) => {
            const items = section.items.filter(match);
            if (!items.length) return null;
            return (
              <div key={section.title}>
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{section.title}</p>
                <ul className="space-y-0.5">
                  {items.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={async () => {
                          const done = await run(() => api.patch(`/transactions/${txnId}/category`, { account_id: c.id }));
                          if (done !== undefined) setOpen(false);
                        }}
                        className="w-full rounded-lg px-2 py-1.5 text-left hover:bg-muted"
                      >
                        <span className="text-sm font-medium">{c.name}</span>
                        {c.description ? <span className="block text-xs text-muted-foreground">{c.description}</span> : null}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
        <ErrorNote message={error} />
      </DialogContent>
    </Dialog>
  );
}

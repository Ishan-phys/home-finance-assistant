"use client";

import { useEffect, useState } from "react";
import { ErrorNote } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, type Categories, type RuleSuggestion } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction, useApi } from "@/lib/use-api";

interface Choice {
  id: string;
  name: string;
  description: string | null;
}

/** Pick the category for a transaction. The bank's own narration is shown above the choices, so
 * the owner can tell what the row is. Every category shows what it is for, and the choice is
 * remembered for the same description in later statements. "Always do this" turns the choice
 * into a rule for every narration containing some text. */
export function CategoryPicker({ txnId, current, narration }: { txnId: string; current: string | null; narration?: string | null }) {
  const { version, refresh } = usePerson();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [always, setAlways] = useState(false);
  const [edited, setEdited] = useState<string | null>(null);
  const [matches, setMatches] = useState<number | null>(null);
  const cats = useApi<Categories>(open ? "/categories" : null, version);
  const suggestion = useApi<RuleSuggestion>(open && always ? `/transactions/${txnId}/rule-suggestion` : null, version);
  const { run, error, busy } = useAction(refresh);

  const matchText = edited ?? suggestion.data?.match_text ?? "";
  const text = matchText.trim();
  const way = suggestion.data?.way ?? "any";
  useEffect(() => {
    if (!always || !text) return;
    let cancelled = false;
    api
      .post<{ matches: number }>("/rules/match-count", { match_text: text, way })
      .then((r) => !cancelled && setMatches(r.matches))
      .catch(() => !cancelled && setMatches(null));
    return () => {
      cancelled = true;
    };
  }, [always, text, way]);

  const q = query.trim().toLowerCase();
  const match = (c: Choice) => !q || c.name.toLowerCase().includes(q) || (c.description ?? "").toLowerCase().includes(q);
  const sections: { title: string; items: Choice[] }[] = cats.data
    ? [
        { title: "Money out", items: cats.data.out.filter((c) => !c.retired) },
        { title: "Money in", items: cats.data.in.filter((c) => !c.retired) },
        { title: "Between your accounts", items: cats.data.own_move?.id ? [cats.data.own_move] : [] },
      ]
    : [];

  async function choose(c: Choice) {
    const done = await run(async () => {
      const changed = await api.patch(`/transactions/${txnId}/category`, { account_id: c.id });
      if (always && text) {
        await api.post("/rules", { label: text, match_text: text, way, target_id: c.id, apply_now: true });
      }
      return changed;
    });
    if (done !== undefined) setOpen(false);
  }

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
        {narration ? (
          <p className="break-all rounded-lg bg-muted/50 px-2.5 py-2 font-mono text-xs" aria-label="Bank narration">
            {narration}
          </p>
        ) : null}
        <Input autoFocus placeholder="Search categories" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="space-y-1.5 rounded-lg border px-2.5 py-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
            Always do this for narrations containing
          </label>
          {always ? (
            <>
              <Input aria-label="Text to match" value={matchText} onChange={(e) => setEdited(e.target.value)} placeholder="Text to match" />
              <p className="text-xs text-muted-foreground">
                {text ? (matches === null ? "Checking…" : `Matches ${matches} existing transaction${matches === 1 ? "" : "s"}, and later statements.`) : "Type the text to match."}
              </p>
            </>
          ) : null}
        </div>
        <div className="max-h-[40vh] space-y-4 overflow-y-auto">
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
                        disabled={busy || (always && !text)}
                        onClick={() => void choose(c)}
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

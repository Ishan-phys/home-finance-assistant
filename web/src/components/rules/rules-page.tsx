"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState, ErrorNote, Loading, NativeSelect, PageHeader } from "@/components/common/shared";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type Categories, type RuleItem } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction, useApi } from "@/lib/use-api";

const WAY: Record<RuleItem["way"], string> = { any: "money in or out", debit: "money out", credit: "money in" };
const MODE: Record<RuleItem["mode"], string> = { contains: "contains", starts_with: "starts with" };

/** Add or edit one rule. The match count updates as the text changes. */
function RuleDialog({ rule, cats, onClose }: { rule: RuleItem | null; cats: Categories; onClose: () => void }) {
  const { refresh } = usePerson();
  const [text, setText] = useState(rule?.match_text ?? "");
  const [mode, setMode] = useState<RuleItem["mode"]>(rule?.mode ?? "contains");
  const [way, setWay] = useState<RuleItem["way"]>(rule?.way ?? "any");
  const [target, setTarget] = useState(rule?.target.id ?? "");
  const [label, setLabel] = useState(rule?.label ?? "");
  const [applyNow, setApplyNow] = useState(true);
  const [matches, setMatches] = useState<number | null>(null);
  const { run, error, busy } = useAction(refresh);
  const trimmed = text.trim();

  useEffect(() => {
    if (!trimmed) return;
    let cancelled = false;
    api
      .post<{ matches: number }>("/rules/match-count", { match_text: trimmed, mode, way })
      .then((r) => !cancelled && setMatches(r.matches))
      .catch(() => !cancelled && setMatches(null));
    return () => {
      cancelled = true;
    };
  }, [trimmed, mode, way]);

  const live = (c: { retired?: boolean }) => !c.retired;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{rule ? "Edit rule" : "Add a rule"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-[8rem_1fr] gap-2">
            <div className="space-y-1">
              <Label htmlFor="rule-mode">Narration</Label>
              <NativeSelect id="rule-mode" className="w-full" value={mode} onChange={(e) => setMode(e.target.value as RuleItem["mode"])}>
                <option value="contains">contains</option>
                <option value="starts_with">starts with</option>
              </NativeSelect>
            </div>
            <div className="space-y-1">
              <Label htmlFor="rule-text">Text</Label>
              <Input id="rule-text" autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Vikram Kapoor" />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {trimmed ? (matches === null ? "Checking…" : `Matches ${matches} existing transaction${matches === 1 ? "" : "s"}.`) : "Case does not matter."}
          </p>
          <div className="space-y-1">
            <Label htmlFor="rule-way">Applies to</Label>
            <NativeSelect id="rule-way" className="w-full" value={way} onChange={(e) => setWay(e.target.value as RuleItem["way"])}>
              <option value="any">money in or out</option>
              <option value="debit">money out only</option>
              <option value="credit">money in only</option>
            </NativeSelect>
          </div>
          <div className="space-y-1">
            <Label htmlFor="rule-target">Category</Label>
            <NativeSelect id="rule-target" className="w-full" value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Pick a category</option>
              <optgroup label="Money out">
                {cats.out.filter(live).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </optgroup>
              <optgroup label="Money in">
                {cats.in.filter(live).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </optgroup>
              {cats.own_move?.id ? (
                <optgroup label="Between your accounts">
                  <option value={cats.own_move.id}>{cats.own_move.name} (card bill payments)</option>
                </optgroup>
              ) : null}
            </NativeSelect>
          </div>
          <div className="space-y-1">
            <Label htmlFor="rule-label">Name (optional)</Label>
            <Input id="rule-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Shown as the payee, e.g. Rent" />
          </div>
          {!rule ? (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={applyNow} onChange={(e) => setApplyNow(e.target.checked)} />
              Also apply to existing transactions (never ones you set by hand)
            </label>
          ) : null}
        </div>
        <ErrorNote message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            disabled={!trimmed || !target || busy}
            onClick={async () => {
              const body = { match_text: trimmed, mode, way, target_id: target, label };
              const done = await run(() =>
                rule ? api.patch(`/rules/${rule.id}`, body) : api.post("/rules", { ...body, apply_now: applyNow }),
              );
              if (done !== undefined) onClose();
            }}
          >
            {rule ? "Save" : "Add rule"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function RulesPage() {
  const { version, refresh } = usePerson();
  const rules = useApi<RuleItem[]>("/rules", version);
  const cats = useApi<Categories>("/categories", version);
  const [editing, setEditing] = useState<RuleItem | "new" | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const action = useAction(refresh);

  if (!rules.data || !cats.data) {
    return rules.error || cats.error ? <ErrorNote message={rules.error ?? cats.error} /> : <Loading what="rules" />;
  }
  const list = rules.data;

  function move(i: number, by: -1 | 1) {
    const ids = list.map((r) => r.id);
    [ids[i], ids[i + by]] = [ids[i + by], ids[i]];
    void action.run(() => api.post("/rules/reorder", { ids }));
  }

  return (
    <div>
      <PageHeader
        title="Rules"
        subtitle="If a narration matches, the transaction goes to the category you choose, before any guessing. The first matching rule wins, from the top."
        action={<Button onClick={() => setEditing("new")}>＋ Add rule</Button>}
      />
      <ErrorNote message={action.error} />
      {note ? <p className="mb-3 text-sm text-muted-foreground">{note}</p> : null}
      {!list.length ? (
        <EmptyState title="No rules yet.">Choose a category on any transaction and tick “Always do this”, or add one here.</EmptyState>
      ) : (
        <ul aria-label="Rules" className="divide-y rounded-xl border">
          {list.map((r, i) => (
            <li key={r.id} className="flex flex-wrap items-center gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {r.label}
                  {r.builtin ? <Badge variant="secondary" className="ml-2">starter</Badge> : null}
                </p>
                <p className="break-all text-xs text-muted-foreground">
                  {MODE[r.mode]} “{r.match_text}” · {WAY[r.way]} → {r.target.name}
                </p>
              </div>
              <div className="flex gap-1">
                <Button variant="ghost" size="xs" aria-label={`Move ${r.label} up`} disabled={i === 0 || action.busy} onClick={() => move(i, -1)}>
                  <ArrowUp className="size-3.5" />
                </Button>
                <Button variant="ghost" size="xs" aria-label={`Move ${r.label} down`} disabled={i === list.length - 1 || action.busy} onClick={() => move(i, 1)}>
                  <ArrowDown className="size-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="xs"
                  disabled={action.busy}
                  onClick={async () => {
                    const res = await action.run(() => api.post<{ changed: number }>(`/rules/${r.id}/apply`));
                    if (res) setNote(`${res.changed} transaction${res.changed === 1 ? "" : "s"} moved by “${r.label}”.`);
                  }}
                >
                  Apply now
                </Button>
                <Button variant="ghost" size="xs" onClick={() => setEditing(r)}>Edit</Button>
                <Button variant="ghost" size="xs" aria-label={`Delete ${r.label}`} disabled={action.busy} onClick={() => void action.run(() => api.delete(`/rules/${r.id}`))}>
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {editing ? <RuleDialog rule={editing === "new" ? null : editing} cats={cats.data} onClose={() => setEditing(null)} /> : null}
    </div>
  );
}

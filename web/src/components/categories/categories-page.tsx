"use client";

import { useState } from "react";
import { CategoryForm } from "@/components/setup/category-form";
import { ErrorNote, Loading, NativeSelect, PageHeader } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { api, type Categories, type Category } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction, useApi } from "@/lib/use-api";
import { CategoryList } from "./category-list";

function MergeDialog({ from, choices, onClose }: { from: Category; choices: Category[]; onClose: () => void }) {
  const { refresh } = usePerson();
  const [into, setInto] = useState("");
  const { run, error, busy } = useAction(refresh);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Merge {from.name}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Every transaction in {from.name} moves to the category you pick, and so do later statements. {from.name} is
          then retired.
        </p>
        <div className="space-y-1">
          <Label htmlFor="merge-into">Merge into</Label>
          <NativeSelect id="merge-into" className="w-full" value={into} onChange={(e) => setInto(e.target.value)}>
            <option value="">Pick a category</option>
            {choices.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </NativeSelect>
        </div>
        <ErrorNote message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            disabled={!into || busy}
            onClick={async () => {
              const done = await run(() => api.post(`/categories/${from.id}/merge`, { into_id: into }));
              if (done !== undefined) onClose();
            }}
          >
            Merge
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function CategoriesPage() {
  const { version, refresh } = usePerson();
  const cats = useApi<Categories>("/categories", version);
  const [adding, setAdding] = useState(false);
  const [merging, setMerging] = useState<Category | null>(null);
  const action = useAction(refresh);

  if (!cats.data) return cats.error ? <ErrorNote message={cats.error} /> : <Loading what="categories" />;
  const data = cats.data;

  const actions = (c: Category) => (
    <div className="flex gap-1">
      <span className="mr-2 self-center text-xs tabular-nums text-muted-foreground">{c.this_month.paise ? c.this_month.formatted : ""}</span>
      <Button variant="ghost" size="xs" aria-label={`Merge ${c.name}`} onClick={() => setMerging(c)}>Merge</Button>
      <Button variant="ghost" size="xs" aria-label={`Retire ${c.name}`} onClick={() => void action.run(() => api.post(`/categories/${c.id}/retire`))}>
        Retire
      </Button>
      <Button
        variant="ghost"
        size="xs"
        aria-label={`Delete ${c.name}`}
        disabled={c.used > 0}
        title={c.used > 0 ? "It has transactions: merge it instead" : undefined}
        onClick={() => void action.run(() => api.delete(`/categories/${c.id}`))}
      >
        Delete
      </Button>
    </div>
  );

  return (
    <div>
      <PageHeader
        title="Categories"
        subtitle="The buckets your money is sorted into. Click a name or a description to change it."
        action={<Button onClick={() => setAdding(true)}>＋ Add category</Button>}
      />
      <ErrorNote message={action.error} />
      <div className="space-y-6">
        <CategoryList title="Money out" items={data.out} onChanged={refresh} actions={actions} />
        <CategoryList title="Money in" items={data.in} onChanged={refresh} actions={actions} />
      </div>
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add a category</DialogTitle>
          </DialogHeader>
          <CategoryForm categories={data} onAdded={() => { setAdding(false); refresh(); }} />
        </DialogContent>
      </Dialog>
      {merging ? (
        <MergeDialog
          from={merging}
          choices={(merging.direction === "in" ? data.in : data.out).filter((c) => !c.retired && c.id !== merging.id)}
          onClose={() => setMerging(null)}
        />
      ) : null}
    </div>
  );
}

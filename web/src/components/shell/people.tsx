"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type Person } from "@/lib/api";
import { useAction } from "@/lib/use-api";
import { ErrorNote, NativeSelect } from "@/components/common/shared";

/** Name a person (and anyone whose name must never reach a model) and create their ledger. */
export function PersonForm({
  onCreated,
  submitLabel = "Create",
}: {
  onCreated: (p: Person) => void;
  submitLabel?: string;
}) {
  const [name, setName] = useState("");
  const [family, setFamily] = useState("");
  const { run, error, busy } = useAction(() => {});

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        const created = await run(() =>
          api.post<Person>("/people", {
            name,
            family_names: family
              .split(",")
              .map((f) => f.trim())
              .filter(Boolean),
          }),
        );
        if (created) {
          setName("");
          setFamily("");
          onCreated(created);
        }
      }}
    >
      <div className="space-y-1">
        <Label htmlFor="person-name">Your name</Label>
        <Input id="person-name" required value={name} onChange={(e) => setName(e.target.value)} />
        <p className="text-xs text-muted-foreground">
          Used only on this machine. It is also added to the names that are always removed from statements before anything
          is stored or sent to a model.
        </p>
      </div>
      <div className="space-y-1">
        <Label htmlFor="person-family">Family names to remove too (optional, comma separated)</Label>
        <Input id="person-family" value={family} onChange={(e) => setFamily(e.target.value)} placeholder="Spouse, parents" />
      </div>
      <ErrorNote message={error} />
      <Button type="submit" disabled={busy || !name.trim()}>
        {submitLabel}
      </Button>
    </form>
  );
}

export function PersonSwitcher({
  people,
  current,
  onSelect,
}: {
  people: Person[];
  current: string;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex items-center gap-2">
      {people.length > 1 ? (
        <>
          <label htmlFor="person-switcher" className="text-sm text-muted-foreground">
            Viewing
          </label>
          <NativeSelect id="person-switcher" value={current} onChange={(e) => onSelect(e.target.value)}>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
        </>
      ) : (
        <span className="text-sm text-muted-foreground">{people[0]?.name}</span>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger render={<Button size="sm" variant="ghost">Add person</Button>} />
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add a person</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Each person has their own ledger. Nothing is shared between people.
          </p>
          <PersonForm
            onCreated={(p) => {
              setOpen(false);
              onSelect(p.id);
            }}
            submitLabel="Create person"
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}

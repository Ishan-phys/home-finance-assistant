"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorText, type Person } from "@/lib/api";
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

/** Delete a person and their whole ledger. The owner types the name first, because there is no
 * undo and the person's statements, rules and privacy terms all go with them. */
function DeletePersonDialog({
  person,
  open,
  onOpenChange,
  onDeleted,
}: {
  person: Person;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {open ? <DeletePersonBody person={person} onClose={() => onOpenChange(false)} onDeleted={onDeleted} /> : null}
      </DialogContent>
    </Dialog>
  );
}

// Mounted only while open, so each opening starts with an empty confirmation.
function DeletePersonBody({ person, onClose, onDeleted }: { person: Person; onClose: () => void; onDeleted: () => void }) {
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const matches = typed.trim().toLowerCase() === person.name.trim().toLowerCase();
  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!matches) return;
        setBusy(true);
        setError(null);
        try {
          await api.delete(`/people/${person.id}`);
        } catch (err) {
          setError(errorText(err));
          setBusy(false);
          return;
        }
        onClose();
        onDeleted();
      }}
    >
      <DialogHeader>
        <DialogTitle>Delete {person.name}?</DialogTitle>
      </DialogHeader>
      <div className="space-y-2 text-sm text-muted-foreground">
        <p>
          This removes {person.name}&apos;s accounts, transactions, uploaded statements, rules and privacy names. Nothing
          is shared between people, so no one else changes. This cannot be undone.
        </p>
      </div>
      <div className="space-y-1">
        <Label htmlFor="delete-person-confirm">Type {person.name} to confirm</Label>
        <Input id="delete-person-confirm" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
      </div>
      <ErrorNote message={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>
          Keep {person.name}
        </Button>
        <Button type="submit" variant="destructive" disabled={busy || !matches}>
          {busy ? "Deleting…" : "Delete person"}
        </Button>
      </div>
    </form>
  );
}

export function PersonSwitcher({
  people,
  current,
  onSelect,
  onDeleted,
}: {
  people: Person[];
  current: string;
  onSelect: (id: string) => void;
  onDeleted: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const currentPerson = people.find((p) => p.id === current);
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
      {people.length > 1 ? (
        <>
          <label htmlFor="person-switcher" className="text-sm text-muted-foreground">
            Viewing
          </label>
          <NativeSelect id="person-switcher" className="min-w-0 flex-1" value={current} onChange={(e) => onSelect(e.target.value)}>
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
      {currentPerson ? (
        <>
          <Button size="sm" variant="ghost" className="text-muted-foreground" onClick={() => setDeleting(true)}>
            Delete person
          </Button>
          <DeletePersonDialog person={currentPerson} open={deleting} onOpenChange={setDeleting} onDeleted={onDeleted} />
        </>
      ) : null}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger render={<Button size="sm" variant="ghost" className="-ml-2">Add person</Button>} />
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

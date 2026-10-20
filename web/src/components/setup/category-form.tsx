"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorNote, NativeSelect } from "@/components/common/shared";
import { api, type Category, type Categories } from "@/lib/api";
import { useAction } from "@/lib/use-api";

/** A new category: its name, whether money goes out or comes in, where it sits, and a line on
 * what it is for. The line also tells the categorizer what belongs here. */
export function CategoryForm({ categories, onAdded }: { categories: Categories; onAdded: (c: Category) => void }) {
  const [name, setName] = useState("");
  const [direction, setDirection] = useState<"out" | "in">("out");
  const [parent, setParent] = useState("");
  const [description, setDescription] = useState("");
  const { run, error, busy } = useAction(() => {});
  const parents = (direction === "out" ? categories.out : categories.in).filter((c) => !c.retired);

  return (
    <form
      aria-label="Add a category"
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        const added = await run(() =>
          api.post<Category>("/categories", { name, direction, description, parent_id: parent || null }),
        );
        if (added) {
          setName("");
          setDescription("");
          setParent("");
          onAdded(added);
        }
      }}
    >
      <div className="space-y-1">
        <Label htmlFor="category-name">Name</Label>
        <Input id="category-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Gym" />
      </div>
      <fieldset className="space-y-1">
        <legend className="text-sm font-medium">This is money</legend>
        <div className="flex gap-4 text-sm">
          {(["out", "in"] as const).map((d) => (
            <label key={d} className="flex items-center gap-1.5">
              <input type="radio" name="direction" value={d} checked={direction === d} onChange={() => setDirection(d)} />
              {d === "out" ? "going out" : "coming in"}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="space-y-1">
        <Label htmlFor="category-parent">Inside (optional)</Label>
        <NativeSelect id="category-parent" className="w-full" value={parent} onChange={(e) => setParent(e.target.value)}>
          <option value="">Nothing: a top-level category</option>
          {parents.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div className="space-y-1">
        <Label htmlFor="category-description">What is it for?</Label>
        <Input
          id="category-description"
          required
          maxLength={200}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Memberships and classes at gyms and studios"
        />
      </div>
      <ErrorNote message={error} />
      <Button type="submit" disabled={busy || !name.trim() || !description.trim()}>
        Add category
      </Button>
    </form>
  );
}

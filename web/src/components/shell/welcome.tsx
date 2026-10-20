"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ErrorNote } from "@/components/common/shared";
import { api } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction } from "@/lib/use-api";
import { PersonForm } from "./people";

/** The first run: nobody exists yet. */
export function Welcome() {
  const { reloadPeople } = usePerson();
  const router = useRouter();
  const sample = useAction(() => {});

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-8 px-4 py-12">
      <div>
        <p className="text-sm font-semibold text-muted-foreground">AI CFO</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Your money, in one honest ledger</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Add your accounts, upload their statements, and see what you own, what you owe and where it went. Everything
          stays on this machine.
        </p>
      </div>
      <div className="rounded-xl border p-5">
        <PersonForm
          submitLabel="Get started"
          onCreated={async (p) => {
            await reloadPeople(p.id);
            router.push("/setup");
          }}
        />
      </div>
      <div className="text-center text-sm text-muted-foreground">
        <p>Want to look around first?</p>
        <Button
          variant="link"
          disabled={sample.busy}
          onClick={async () => {
            const created = await sample.run(() => api.post<{ person_id: string }>("/sample"));
            if (created) {
              await reloadPeople(created.person_id);
              router.push("/");
            }
          }}
        >
          Load sample statements
        </Button>
        <ErrorNote message={sample.error} />
      </div>
    </main>
  );
}

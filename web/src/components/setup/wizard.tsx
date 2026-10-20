"use client";

import { Check } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { CategoryList } from "@/components/categories/category-list";
import { Amount, ErrorNote, Loading } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { api, type BalanceSheet, type Catalog, type Categories } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction, useApi } from "@/lib/use-api";
import { AccountForm } from "./account-form";
import { CategoryForm } from "./category-form";

const STEPS = ["welcome", "accounts", "categories", "done"] as const;
type Step = (typeof STEPS)[number];

const WHY: Record<Step, string> = {
  welcome: "Let's set up your books. It takes about two minutes.",
  accounts: "Add the accounts you want to track. Statements are uploaded into these.",
  categories: "These are the buckets your spending and income are sorted into. Adjust them or add your own.",
  done: "You're set up. Add a statement to see your numbers.",
};

const TITLE: Record<Step, string> = {
  welcome: "Welcome",
  accounts: "Your accounts",
  categories: "Your categories",
  done: "Done",
};

export function SetupWizard() {
  const params = useSearchParams();
  const router = useRouter();
  const { person, version, refresh, setup } = usePerson();
  const initial = (STEPS as readonly string[]).includes(params.get("step") ?? "") ? (params.get("step") as Step) : "welcome";
  const [step, setStep] = useState<Step>(initial);
  const index = STEPS.indexOf(step);
  const catalog = useApi<Catalog>("/catalog", 0);
  const sheet = useApi<BalanceSheet>("/reports/balance-sheet", version);
  const categories = useApi<Categories>("/categories", version);
  const finish = useAction(refresh);
  const [adding, setAdding] = useState(false);
  const accounts = (sheet.data?.groups ?? []).flatMap((g) => g.accounts).filter((a) => a.role === "real");
  const revisiting = setup?.completed;

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          Step {index + 1} of {STEPS.length}
        </p>
        <ol className="flex gap-1.5" aria-label="Progress">
          {STEPS.map((s, i) => (
            <li key={s} className={`h-1.5 flex-1 rounded-full ${i <= index ? "bg-primary" : "bg-muted"}`} aria-current={s === step ? "step" : undefined}>
              <span className="sr-only">{TITLE[s]}</span>
            </li>
          ))}
        </ol>
        <h1 className="text-2xl font-semibold tracking-tight">{TITLE[step]}</h1>
        <p className="text-sm text-muted-foreground">{WHY[step]}</p>
      </div>

      {step === "welcome" ? (
        <div className="space-y-4">
          <p className="text-sm">
            Hi {person?.name}. You will add the accounts you hold (savings, cards, deposits, investments), check the
            categories your money is sorted into, and then upload statements. Your name is removed from every statement
            before anything is stored or sent to a model.
          </p>
          <Button onClick={() => setStep("accounts")}>Continue</Button>
        </div>
      ) : null}

      {step === "accounts" ? (
        <div className="space-y-6">
          {accounts.length ? (
            <ul aria-label="Accounts added" className="divide-y rounded-xl border">
              {accounts.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                  <span>
                    <span className="font-medium">{a.name}</span>
                    <span className="text-muted-foreground"> · {a.type_label} · {a.institution}</span>
                  </span>
                  {a.manual || !a.binding ? a.balance ? <Amount value={a.balance} /> : null : (
                    <span className="text-xs text-muted-foreground">statements</span>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="rounded-xl border p-4">
            {catalog.data ? <AccountForm catalog={catalog.data} onAdded={() => refresh()} /> : <Loading what="account types" />}
          </div>
          <div className="flex gap-2">
            <Button disabled={!accounts.length} onClick={() => (revisiting ? router.push("/") : setStep("categories"))}>
              {revisiting ? "Done" : "Continue"}
            </Button>
            {!accounts.length ? <p className="self-center text-xs text-muted-foreground">Add at least one account to continue.</p> : null}
          </div>
        </div>
      ) : null}

      {step === "categories" ? (
        <div className="space-y-6">
          {categories.data ? (
            <>
              <CategoryList title="Money out" items={categories.data.out} onChanged={refresh} />
              <CategoryList title="Money in" items={categories.data.in} onChanged={refresh} />
              <Dialog open={adding} onOpenChange={setAdding}>
                <DialogTrigger render={<Button variant="outline">＋ Add category</Button>} />
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Add a category</DialogTitle>
                  </DialogHeader>
                  <CategoryForm
                    categories={categories.data}
                    onAdded={() => {
                      setAdding(false);
                      refresh();
                    }}
                  />
                </DialogContent>
              </Dialog>
            </>
          ) : (
            <Loading what="categories" />
          )}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setStep("accounts")}>
              Back
            </Button>
            <Button onClick={() => setStep("done")}>Use these categories</Button>
          </div>
        </div>
      ) : null}

      {step === "done" ? (
        <div className="space-y-4">
          <ul className="space-y-1 text-sm">
            <li className="flex items-center gap-2">
              <Check className="size-4 text-emerald-600" /> {accounts.length} account{accounts.length === 1 ? "" : "s"}
            </li>
            <li className="flex items-center gap-2">
              <Check className="size-4 text-emerald-600" /> {(categories.data?.out.length ?? 0) + (categories.data?.in.length ?? 0)} categories
            </li>
          </ul>
          <ErrorNote message={finish.error} />
          <Button
            disabled={finish.busy}
            onClick={async () => {
              const done = await finish.run(() => api.post("/setup/complete"));
              if (done === undefined) return;
              const first = accounts.find((a) => a.binding) ?? accounts[0];
              router.push(first ? `/accounts/${first.id}?upload=1` : "/");
            }}
          >
            Add your first statement
          </Button>
        </div>
      ) : null}
    </div>
  );
}

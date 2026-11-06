"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNote } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, errorText } from "@/lib/api";
import { usePerson } from "@/lib/person";

interface Usage {
  postings: number;
  imports: number;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** Delete an account and everything on it, after saying what will go. */
export function DeleteAccountDialog({ open, onOpenChange, ...account }: {
  accountId: string;
  accountName: string;
  institution: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>{open ? <DeleteBody {...account} onClose={() => onOpenChange(false)} /> : null}</DialogContent>
    </Dialog>
  );
}

// Mounted only while the dialog is open, so each opening starts from a clean state and asks again.
function DeleteBody({ accountId, accountName, institution, onClose }: {
  accountId: string;
  accountName: string;
  institution: string | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const { refresh } = usePerson();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get<Usage>(`/accounts/${accountId}/usage`)
      .then((u) => !cancelled && setUsage(u))
      .catch((e) => !cancelled && setUsageError(errorText(e)));
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  const label = [institution, accountName].filter(Boolean).join(" · ");
  return (
    <>
      <DialogHeader>
        <DialogTitle>Delete {accountName}?</DialogTitle>
      </DialogHeader>
      <div className="space-y-2 text-sm text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">{label}</span>
        </p>
        {usage ? (
          <p>
            This removes the account, its {plural(usage.postings, "transaction", "transactions")} and its{" "}
            {plural(usage.imports, "uploaded statement", "uploaded statements")}.
          </p>
        ) : usageError ? null : (
          <p>Checking what is in this account…</p>
        )}
        <p>
          A movement between this account and another one stays on the other account, waiting for its other side to
          be uploaded. Your other accounts are not changed. This cannot be undone, but you can add the account and
          upload its statements again.
        </p>
      </div>
      <ErrorNote message={usageError ?? error} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Keep it</Button>
        <Button
          variant="destructive"
          disabled={busy || usage === null}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await api.delete(`/accounts/${accountId}`);
            } catch (e) {
              setError(errorText(e));
              setBusy(false);
              return;
            }
            onClose();
            router.push("/accounts");
            refresh();
          }}
        >
          Delete account
        </Button>
      </div>
    </>
  );
}

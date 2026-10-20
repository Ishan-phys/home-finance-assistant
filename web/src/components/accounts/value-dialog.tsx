"use client";

import { useState } from "react";
import { ErrorNote } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, toPaise } from "@/lib/api";
import { useAction } from "@/lib/use-api";

/** A new value for an account without statements (a deposit, property, gold). */
export function ValueDialog({ accountId, open, onOpenChange, onSaved }: {
  accountId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const [amount, setAmount] = useState("");
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const { run, error, busy } = useAction(onSaved);
  const paise = toPaise(amount);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Update value</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (paise === null) return;
            const done = await run(() => api.post(`/accounts/${accountId}/value`, { as_of: asOf, amount_paise: paise }));
            if (done !== undefined) onOpenChange(false);
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="value-amount">What it is worth ₹</Label>
            <Input id="value-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="value-asof">As of</Label>
            <Input id="value-asof" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </div>
          <p className="text-xs text-muted-foreground">The change counts toward net worth, not toward income.</p>
          <ErrorNote message={error} />
          <Button type="submit" disabled={busy || paise === null}>Save</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

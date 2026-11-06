"use client";

import { useCallback, useState } from "react";
import { Amount, ErrorNote, Loading } from "@/components/common/shared";
import { useUndo } from "@/components/common/undo-toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { api, errorText, type CardOption, type CardOptions, type CardPaid, type Money } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useApi } from "@/lib/use-api";

/** Record a bank row as a payment to a card, and say so with an Undo for a short while. A wrong
 * card is put right by picking again, or by Undo, which puts the row back exactly as it was. */
export function useCardPayment(txnId: string, amount: Money | null) {
  const { refresh } = usePerson();
  const { offer } = useUndo();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pay = useCallback(
    async (card: CardOption): Promise<boolean> => {
      setBusy(true);
      setError(null);
      try {
        const paid = await api.post<CardPaid>(`/transactions/${txnId}/card-payment`, { card_id: card.id });
        refresh();
        const what = amount ? `${amount.formatted} recorded` : "Recorded";
        if (paid.matched) {
          offer(`${what} as a payment to ${paid.card}. Its statement already shows it.`);
        } else {
          offer(`${what} as a payment to ${paid.card}. ${paid.card} owes that much less.`, async () => {
            await api.post(`/transactions/${txnId}/card-payment/undo`, paid.previous);
            refresh();
          });
        }
        return true;
      } catch (e) {
        setError(errorText(e));
        return false;
      } finally {
        setBusy(false);
      }
    },
    [txnId, amount, refresh, offer],
  );
  return { pay, error, busy };
}

/** The cards a row could have paid, the likeliest first. Nothing is recorded until one is clicked. */
export function CardChoices({ txnId, options, disabled, onDone }: {
  txnId: string;
  options: CardOptions;
  disabled?: boolean;
  onDone: () => void;
}) {
  const { pay, error, busy } = useCardPayment(txnId, options.amount);
  return (
    <div>
      <ul className="space-y-0.5" aria-label="Credit cards">
        {options.cards.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              disabled={busy || disabled || c.current}
              onClick={async () => {
                if (await pay(c)) onDone();
              }}
              className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-muted disabled:opacity-60"
            >
              <span>
                <span className="text-sm font-medium">{c.name}</span>
                <span className="block text-xs text-muted-foreground">
                  Owes <Amount value={c.owed} /> now
                </span>
              </span>
              {c.current ? (
                <Badge variant="secondary">Chosen now</Badge>
              ) : c.suggested ? (
                <Badge>Matches this payment</Badge>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
      <ErrorNote message={error} />
    </div>
  );
}

/** The inbox's button for money that left a bank account for "an account of yours". */
export function PayCardButton({ txnId, narration }: { txnId: string; narration: string | null }) {
  const { version } = usePerson();
  const [open, setOpen] = useState(false);
  const options = useApi<CardOptions>(open ? `/transactions/${txnId}/card-options` : null, version);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm">Pay a card</Button>} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Which card did this pay?</DialogTitle>
        </DialogHeader>
        {narration ? (
          <p className="break-all rounded-lg bg-muted/50 px-2.5 py-2 font-mono text-xs" aria-label="Bank narration">
            {narration}
          </p>
        ) : null}
        {options.data ? (
          options.data.cards.length ? (
            <>
              <p className="text-sm text-muted-foreground">
                Pick the card and it owes that much less straight away. You can undo it for a short while, and the
                card&apos;s statement takes over when you upload it.
              </p>
              <CardChoices txnId={txnId} options={options.data} onDone={() => setOpen(false)} />
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              There is no credit card to pick. Add one in Accounts first, or this payment is not money that left a bank
              account.
            </p>
          )
        ) : options.error ? (
          <ErrorNote message={options.error} />
        ) : (
          <Loading what="your cards" />
        )}
      </DialogContent>
    </Dialog>
  );
}

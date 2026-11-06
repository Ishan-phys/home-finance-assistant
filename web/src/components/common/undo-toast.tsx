"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { errorText } from "@/lib/api";
import { usePerson } from "@/lib/person";

/** How long an action can be taken back. Long enough to notice a wrong pick, short enough that
 * the books are not left open to changing. */
export const UNDO_SECONDS = 45;
const NOTE_SECONDS = 6;

interface Toast {
  message: string;
  undo: (() => Promise<void>) | null;
  until: number;
}

interface UndoApi {
  /** Say what just happened. With `undo`, offer to take it back for a short while. */
  offer: (message: string, undo?: () => Promise<void>) => void;
}

const Ctx = createContext<UndoApi | null>(null);

export function useUndo(): UndoApi {
  const found = useContext(Ctx);
  if (!found) throw new Error("useUndo must be used inside UndoProvider");
  return found;
}

/** One message at a time, bottom centre of every page, so it outlives the row that caused it.
 * Keyed by person: an undo always goes to the ledger the action was made in. */
export function UndoProvider({ children }: { children: ReactNode }) {
  const { person } = usePerson();
  return <Scope key={person?.id ?? "none"}>{children}</Scope>;
}

function Scope({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const [left, setLeft] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const offer = useCallback((message: string, undo?: () => Promise<void>) => {
    const seconds = undo ? UNDO_SECONDS : NOTE_SECONDS;
    setError(null);
    setLeft(seconds);
    setToast({ message, undo: undo ?? null, until: Date.now() + seconds * 1000 });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = setInterval(() => {
      const seconds = Math.ceil((toast.until - Date.now()) / 1000);
      if (seconds <= 0) setToast(null);
      else setLeft(seconds);
    }, 500);
    return () => clearInterval(id);
  }, [toast]);

  const api = useMemo(() => ({ offer }), [offer]);

  async function undo() {
    if (!toast?.undo) return;
    setBusy(true);
    setError(null);
    try {
      await toast.undo();
      offer("Undone. Nothing else changed.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Ctx.Provider value={api}>
      {children}
      {toast ? (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-4 left-1/2 z-50 flex w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 items-center gap-3 rounded-xl border bg-background px-4 py-3 text-sm shadow-lg"
        >
          <div className="min-w-0 flex-1">
            <p>{toast.message}</p>
            {error ? <p className="text-xs text-destructive">{error}</p> : null}
            {toast.undo ? <p className="text-xs text-muted-foreground">You can undo this for {left} more seconds.</p> : null}
          </div>
          {toast.undo ? (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void undo()}>
              Undo
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" aria-label="Dismiss" onClick={() => setToast(null)}>
            ✕
          </Button>
        </div>
      ) : null}
    </Ctx.Provider>
  );
}

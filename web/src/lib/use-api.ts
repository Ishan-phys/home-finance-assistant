"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";

interface Settled<T> {
  key: string;
  data: T | null;
  error: string | null;
}

/** Fetch a path; refetch when `version` (bumped after any write) or the path changes.
 * The previous data stays visible while a refetch is in flight. */
export function useApi<T>(path: string | null, version: number) {
  const key = `${path}#${version}`;
  const [state, setState] = useState<Settled<T>>({ key: "", data: null, error: null });

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    api
      .get<T>(path)
      .then((data) => !cancelled && setState({ key, data, error: null }))
      .catch((e) => !cancelled && setState((prev) => ({ key, data: prev.data, error: errorText(e) })));
    return () => {
      cancelled = true;
    };
  }, [path, key]);

  return { data: state.data, error: state.error, loading: path !== null && state.key !== key };
}

/** Run a write, report failures, and refresh on success. */
export function useAction(refresh: () => void) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = useCallback(
    async <R,>(fn: () => Promise<R>): Promise<R | undefined> => {
      setBusy(true);
      setError(null);
      try {
        const result = await fn();
        refresh();
        return result;
      } catch (e) {
        setError(errorText(e));
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );
  return { run, error, busy, clear: () => setError(null) };
}

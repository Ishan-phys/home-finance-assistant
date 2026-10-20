"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setCurrentPerson, type Person, type SetupState } from "@/lib/api";

const STORAGE_KEY = "cfo.person";

interface PersonState {
  /** null until the people list has loaded. */
  people: Person[] | null;
  person: Person | null;
  setup: SetupState | null;
  /** True while the setup state shown is from before the latest write. */
  setupStale: boolean;
  /** Bumped after every write, so every view refetches and figures never go stale. */
  version: number;
  refresh: () => void;
  select: (id: string) => void;
  reloadPeople: (select?: string) => Promise<void>;
}

const Ctx = createContext<PersonState | null>(null);

function remembered(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function remember(id: string) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* private mode: the choice lasts for this page only */
  }
}

interface Loaded<T> {
  key: string;
  value: T;
}

export function PersonProvider({ children }: { children: ReactNode }) {
  const [people, setPeople] = useState<Person[] | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const [setupFor, setSetupFor] = useState<Loaded<SetupState> | null>(null);
  const [version, setVersion] = useState(0);
  const setupKey = `${current}#${version}`;

  const choose = useCallback((list: Person[], wanted: string | null) => {
    const chosen = list.find((p) => p.id === wanted) ?? list[0] ?? null;
    setCurrentPerson(chosen?.id ?? null);
    setPeople(list);
    setCurrent(chosen?.id ?? null);
    if (chosen) remember(chosen.id);
    setVersion((v) => v + 1);
  }, []);

  const reloadPeople = useCallback(
    async (select?: string) => choose(await api.get<Person[]>("/people"), select ?? remembered()),
    [choose],
  );

  useEffect(() => {
    let cancelled = false;
    api.get<Person[]>("/people").then((list) => !cancelled && choose(list, remembered()));
    return () => {
      cancelled = true;
    };
  }, [choose]);

  useEffect(() => {
    if (!current) return;
    let cancelled = false;
    api
      .get<SetupState>("/setup")
      .then((value) => !cancelled && setSetupFor({ key: setupKey, value }))
      .catch(() => !cancelled && setSetupFor({ key: setupKey, value: { completed: false, accounts: 0 } }));
    return () => {
      cancelled = true;
    };
  }, [current, setupKey]);

  // The setup state of the current person, or null while it is (re)loading.
  const setup = current && setupFor?.key.startsWith(`${current}#`) ? setupFor.value : null;

  const value = useMemo<PersonState>(
    () => ({
      people,
      person: people?.find((p) => p.id === current) ?? null,
      setup,
      setupStale: setupFor?.key !== setupKey,
      version,
      refresh: () => setVersion((v) => v + 1),
      select: (id: string) => {
        setCurrentPerson(id);
        setCurrent(id);
        remember(id);
        setVersion((v) => v + 1);
      },
      reloadPeople,
    }),
    [people, current, setup, setupFor, setupKey, version, reloadPeople],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePerson(): PersonState {
  const found = useContext(Ctx);
  if (!found) throw new Error("usePerson must be used inside PersonProvider");
  return found;
}

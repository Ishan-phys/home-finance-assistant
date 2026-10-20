"use client";

import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/app-shell";
import { PersonProvider } from "@/lib/person";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <PersonProvider>
      <AppShell>{children}</AppShell>
    </PersonProvider>
  );
}

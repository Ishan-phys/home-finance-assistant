"use client";

import type { ReactNode } from "react";
import { AuthGate } from "@/components/auth/auth-gate";
import { UndoProvider } from "@/components/common/undo-toast";
import { AppShell } from "@/components/shell/app-shell";
import { PersonProvider } from "@/lib/person";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <PersonProvider>
        <UndoProvider>
          <AppShell>{children}</AppShell>
        </UndoProvider>
      </PersonProvider>
    </AuthGate>
  );
}

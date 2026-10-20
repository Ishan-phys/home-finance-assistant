"use client";

import { Menu, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { usePerson } from "@/lib/person";
import { AssistantPanel } from "./assistant-panel";
import { Sidebar } from "./sidebar";
import { Welcome } from "./welcome";

/** Sidebar on the left, the page in the main pane, the assistant sliding over from the right.
 * Nobody yet: the welcome screen. Not set up yet: the setup wizard, full width. */
export function AppShell({ children }: { children: ReactNode }) {
  const { people, person, setup, setupStale } = usePerson();
  const path = usePathname();
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  // The drawer belongs to the page it was opened on, so navigating closes it.
  const [drawerAt, setDrawerAt] = useState<string | null>(null);
  const drawer = drawerAt === path;
  const setDrawer = (open: boolean) => setDrawerAt(open ? path : null);
  const inSetup = path.startsWith("/setup");
  const needsSetup = setup !== null && !setup.completed && !setupStale;

  useEffect(() => {
    if (needsSetup && !inSetup) router.replace("/setup");
  }, [needsSetup, inSetup, router]);

  if (people === null) {
    return <p className="p-8 text-sm text-muted-foreground">Loading…</p>;
  }
  if (!person) return <Welcome />;
  if (setup === null) return <p className="p-8 text-sm text-muted-foreground">Loading…</p>;
  if (inSetup || needsSetup) {
    return <main className="mx-auto w-full max-w-3xl px-4 py-10">{needsSetup && !inSetup ? null : children}</main>;
  }

  return (
    <div className="flex min-h-screen">
      <div className="hidden w-64 shrink-0 border-r bg-muted/20 md:block">
        <div className="sticky top-0 h-screen">
          <Sidebar onAsk={() => setAsking(true)} />
        </div>
      </div>

      {drawer ? (
        <div className="fixed inset-0 z-30 md:hidden">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/30" onClick={() => setDrawer(false)} />
          <div className="relative h-full w-72 border-r bg-background">
            <Button variant="ghost" size="icon-sm" aria-label="Close menu" className="absolute right-2 top-3" onClick={() => setDrawer(false)}>
              <X />
            </Button>
            <Sidebar onAsk={() => setAsking(true)} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b px-4 py-2 md:hidden">
          <Button variant="ghost" size="icon-sm" aria-label="Open menu" onClick={() => setDrawer(true)}>
            <Menu />
          </Button>
          <span className="text-sm font-semibold">AI CFO</span>
        </div>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 md:px-8">{children}</main>
      </div>

      <AssistantPanel open={asking} onClose={() => setAsking(false)} />
    </div>
  );
}

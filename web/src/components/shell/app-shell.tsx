"use client";

import { Menu, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Loading } from "@/components/common/shared";
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

  // Escape closes the menu, as it does every other overlay in the app.
  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerAt(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  if (people === null) {
    return <div className="mx-auto max-w-5xl p-8"><Loading what="your books" page /></div>;
  }
  if (!person) return <Welcome />;
  if (setup === null) return <div className="mx-auto max-w-5xl p-8"><Loading what="your books" page /></div>;
  if (inSetup || needsSetup) {
    return <main id="main" className="mx-auto w-full max-w-3xl px-4 py-10">{needsSetup && !inSetup ? null : children}</main>;
  }

  return (
    <div className="flex min-h-screen">
      <div className="hidden w-64 shrink-0 border-r bg-sidebar md:block">
        <div className="sticky top-0 h-screen">
          <Sidebar onAsk={() => setAsking(true)} />
        </div>
      </div>

      {drawer ? (
        <div className="fixed inset-0 z-30 md:hidden">
          <button type="button" aria-label="Close menu" className="scrim-in absolute inset-0 bg-foreground/40 backdrop-blur-[2px]" onClick={() => setDrawer(false)} />
          <div className="drawer-in relative h-full w-[min(20rem,85vw)] border-r bg-sidebar shadow-2xl">
            <Button variant="ghost" size="icon-sm" aria-label="Close menu" className="absolute right-2 top-3" onClick={() => setDrawer(false)}>
              <X />
            </Button>
            <Sidebar onAsk={() => setAsking(true)} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="sticky top-0 z-20 flex items-center gap-2 border-b bg-background/85 px-3 py-1.5 backdrop-blur md:hidden">
          <Button variant="ghost" size="icon-sm" aria-label="Open menu" onClick={() => setDrawer(true)}>
            <Menu />
          </Button>
          <span className="font-heading text-lg font-medium tracking-tight">AI CFO</span>
        </div>
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 outline-none md:px-8 md:py-10">{children}</main>
      </div>

      <AssistantPanel open={asking} onClose={() => setAsking(false)} />
    </div>
  );
}

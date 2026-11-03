"use client";

import { useEffect, useState, type ReactNode } from "react";
import { SIGNED_OUT_EVENT } from "@/lib/auth";
import { SignIn } from "./sign-in";

type Status = "checking" | "in" | "out";

/** Shows the app only to a signed-in owner. Everything inside waits for this check, so no ledger
 * request is made from a signed-out browser. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/me", { cache: "no-store" })
      .then((res) => {
        if (!cancelled) setStatus(res.ok ? "in" : "out");
      })
      .catch(() => {
        if (!cancelled) setStatus("out");
      });
    const signedOut = () => setStatus("out");
    window.addEventListener(SIGNED_OUT_EVENT, signedOut);
    return () => {
      cancelled = true;
      window.removeEventListener(SIGNED_OUT_EVENT, signedOut);
    };
  }, []);

  if (status === "checking") return <p className="p-8 text-sm text-muted-foreground">Loading…</p>;
  if (status === "out") return <SignIn onSignedIn={() => setStatus("in")} />;
  return <>{children}</>;
}

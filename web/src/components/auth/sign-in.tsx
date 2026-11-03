"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** The owner's sign-in form. The server checks the password; nothing is stored in the browser
 * except the session cookie the server sets. */
export function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        cache: "no-store",
      });
      if (res.ok) {
        setPassword("");
        onSignedIn();
        return;
      }
      const body = await res.json().catch(() => null);
      setError(body?.error?.message ?? "Sign-in did not work. Try again.");
    } catch {
      setError("Cannot reach the app. Check that Tailscale is connected, then try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Sign in to AI CFO</h1>
          <p className="text-sm text-muted-foreground">
            Only the owner can sign in. You stay signed in on this device for 5 days.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="username">Username</Label>
          <Input
            id="username"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </main>
  );
}

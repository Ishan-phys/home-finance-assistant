"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/use-api";
import { ErrorNote } from "@/components/common/shared";

interface TokenInfo {
  token: string;
  count: number;
  label: string | null;
}

interface Preview {
  examples: { original: string; sent: string }[];
  aliases: { real: string; alias: string }[];
}

export function PrivacyCard({ version, refresh }: { version: number; refresh: () => void }) {
  const terms = useApi<{ terms: string[] }>("/privacy/terms", version);
  const preview = useApi<Preview>("/privacy/preview", version);
  const tokens = useApi<TokenInfo[]>("/privacy/labels", version);
  const { run, error, busy } = useAction(refresh);
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? (terms.data?.terms ?? []).join("\n");

  return (
    <Card aria-label="Privacy" id="privacy">
      <CardHeader>
        <CardTitle>Privacy: what the model sees</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Personal details are removed when a statement is imported: names, addresses, phone numbers, PAN, account
          numbers and UPI handles become stable tokens, and the original file is never kept. Your account names and the
          categories you named are swapped for aliases before anything goes to a model. Amounts are kept, because the advice depends on them.
          Redaction is best-effort: add your own name and your family&apos;s below so they are always removed.
        </p>
        <form
          className="space-y-2"
          onSubmit={async (e) => {
            e.preventDefault();
            await run(() => api.put("/privacy/terms", { terms: value.split("\n") }));
            setDraft(null);
          }}
        >
          <label htmlFor="terms" className="text-sm font-medium">
            Always redact (one per line)
          </label>
          <Textarea id="terms" rows={3} value={value} onChange={(e) => setDraft(e.target.value)} placeholder="Your full name&#10;A family member" />
          <Button type="submit" size="sm" disabled={busy || draft === null}>
            Save
          </Button>
        </form>
        <ErrorNote message={error ?? terms.error ?? preview.error} />
        <div>
          <h3 className="mb-1 text-sm font-medium">Preview of what would be sent</h3>
          {preview.data && preview.data.examples.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Stored in your ledger</TableHead>
                  <TableHead>Sent to the model</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.data.examples.map((e) => (
                  <TableRow key={e.original}>
                    <TableCell className="max-w-72 truncate font-mono text-xs" title={e.original}>
                      {e.original}
                    </TableCell>
                    <TableCell className="max-w-72 truncate font-mono text-xs" title={e.sent}>
                      {e.sent}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">Import a statement to see a preview.</p>
          )}
        </div>
        {tokens.data && tokens.data.length ? (
          <div>
            <h3 className="mb-1 text-sm font-medium">Names for redacted people and numbers</h3>
            <p className="mb-2 text-xs text-muted-foreground">
              Statements are stored with a stable token for each person, number and handle. Give a token a name to see it
              here in the cockpit. Claude only ever sees the token, never the name you give it.
            </p>
            <div className="max-h-56 space-y-1 overflow-y-auto">
              {tokens.data
                .filter((t) => t.token.startsWith("[PERSON:") || t.token.startsWith("[VPA:"))
                .map((t) => (
                  <div key={t.token} className="flex items-center gap-2 text-sm">
                    <code className="w-28 shrink-0 text-xs">{t.token}</code>
                    <span className="w-10 shrink-0 text-xs text-muted-foreground">×{t.count}</span>
                    <Input
                      aria-label={`Name for ${t.token}`}
                      className="h-7"
                      defaultValue={t.label ?? ""}
                      placeholder="Add a name"
                      onBlur={(e) => {
                        if (e.target.value !== (t.label ?? ""))
                          void run(() => api.put("/privacy/labels", { token: t.token, label: e.target.value }));
                      }}
                    />
                  </div>
                ))}
            </div>
          </div>
        ) : null}
        {preview.data && preview.data.aliases.length ? (
          <div>
            <h3 className="mb-1 text-sm font-medium">Aliases</h3>
            <p className="text-xs text-muted-foreground">
              {preview.data.aliases.map((a) => `${a.real} → ${a.alias}`).join(" · ")}
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

"use client";

import Link from "next/link";
import { useState } from "react";
import { ErrorNote, Warnings } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError, errorText, type UploadResult } from "@/lib/api";

/** Upload one statement. A password field appears only when the file turns out to be protected;
 * the password is used to open the file in memory and is never stored. */
export function UploadDialog({
  accountId,
  accountName,
  open,
  onOpenChange,
  onUploaded,
}: {
  accountId: string;
  accountName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [needsPassword, setNeedsPassword] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function close(next: boolean) {
    if (!next) {
      setFile(null);
      setPassword("");
      setNeedsPassword(false);
      setResult(null);
      setError(null);
    }
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent aria-label="Upload a statement">
        <DialogHeader>
          <DialogTitle>Upload a statement</DialogTitle>
        </DialogHeader>
        {result ? (
          <div className="space-y-3 text-sm">
            <p className="font-medium">{result.rows_inserted} rows added to {accountName}</p>
            <ul className="space-y-0.5 text-muted-foreground">
              {result.hashes_ignored ? <li>{result.hashes_ignored} were already there</li> : null}
              {result.pairs_merged ? <li>{result.pairs_merged} matched a movement from another of your accounts</li> : null}
              {result.uncategorized ? <li>{result.uncategorized} need a category</li> : null}
              {result.gaps ? <li>The statement balance does not match: a statement may be missing</li> : null}
            </ul>
            <Warnings items={result.warnings} />
            <div className="flex gap-2">
              <Button onClick={() => close(false)}>Done</Button>
              {result.uncategorized || result.gaps ? (
                <Button variant="outline" render={<Link href="/inbox" />} onClick={() => close(false)}>
                  Open the Inbox
                </Button>
              ) : null}
            </div>
          </div>
        ) : (
          <form
            className="space-y-3"
            onSubmit={async (e) => {
              e.preventDefault();
              if (!file) return;
              setBusy(true);
              setError(null);
              try {
                const done = await api.upload<UploadResult>(`/accounts/${accountId}/uploads`, file, password || undefined);
                setResult(done);
                onUploaded();
              } catch (err) {
                if (err instanceof ApiError && (err.code === "PASSWORD_REQUIRED" || err.code === "PASSWORD_INVALID")) {
                  setNeedsPassword(true);
                }
                setError(errorText(err));
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="space-y-1">
              <Label htmlFor="statement-file">Statement file</Label>
              <Input id="statement-file" type="file" accept=".csv,.xls,.xlsx,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <p className="text-xs text-muted-foreground">CSV, Excel or PDF, as downloaded from your bank. The file is read in memory and not kept.</p>
            </div>
            {needsPassword ? (
              <div className="space-y-1">
                <Label htmlFor="statement-password">File password</Label>
                <Input id="statement-password" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
            ) : null}
            <ErrorNote message={error} />
            <Button type="submit" disabled={!file || busy}>
              {busy ? "Reading…" : "Upload"}
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Amount, EmptyState, ErrorNote, Loading, PageHeader, shortDate, Stat } from "@/components/common/shared";
import { TxnTable } from "@/components/transactions/txn-table";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type AccountPage, type Statement } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction, useApi } from "@/lib/use-api";
import { UploadDialog } from "./upload-dialog";
import { ValueDialog } from "./value-dialog";

function RemoveStatement({ statement }: { statement: Statement }) {
  const { refresh } = usePerson();
  const [open, setOpen] = useState(false);
  const { run, error, busy } = useAction(refresh);
  return (
    <>
      <Button variant="ghost" size="sm" aria-label={`Remove ${statement.file_name}`} onClick={() => setOpen(true)}>
        Remove
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove {statement.file_name}?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Its {statement.rows_inserted} rows and its balance are removed. A movement it matched in another account goes
            back to waiting for its other side. You can upload the file again later.
          </p>
          <ErrorNote message={error} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>Keep it</Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={async () => {
                const done = await run(() => api.delete(`/imports/${statement.import_id}`));
                if (done !== undefined || !error) setOpen(false);
              }}
            >
              Remove statement
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function AccountView({ id }: { id: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const { version, refresh } = usePerson();
  const page = useApi<AccountPage>(`/accounts/${id}`, version);
  const [uploading, setUploading] = useState(params.get("upload") === "1");
  const [valuing, setValuing] = useState(false);

  if (!page.data) return page.error ? <ErrorNote message={page.error} /> : <Loading what="account" />;
  const { account, register, statements, holdings } = page.data;
  const feed = Boolean(account.binding);

  return (
    <div>
      <PageHeader
        title={account.name}
        subtitle={[account.type_label, account.institution].filter(Boolean).join(" · ")}
        action={
          feed ? (
            <Button onClick={() => setUploading(true)}>Upload statement</Button>
          ) : (
            <Button onClick={() => setValuing(true)}>Update value</Button>
          )
        }
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Stat label={account.kind === "liability" ? "Owed" : "Balance"} value={account.balance ? <Amount value={account.balance} /> : "—"} />
        {holdings ? (
          <>
            <Stat label="Cost" value={<Amount value={holdings.cost} />} />
            <Stat label="Gain not yet realised" value={<Amount value={holdings.unrealized} />} />
          </>
        ) : null}
      </div>

      {feed && !statements.length ? (
        <EmptyState
          title={`Upload your first ${account.name} statement`}
          action={<Button onClick={() => setUploading(true)}>Upload statement</Button>}
        >
          Download it from your bank as CSV, Excel or PDF. Rows become transactions, and the statement&apos;s closing
          balance is checked against them.
        </EmptyState>
      ) : (
        <Tabs defaultValue="transactions">
          <TabsList>
            <TabsTrigger value="transactions">Transactions</TabsTrigger>
            {feed ? <TabsTrigger value="statements">Statements</TabsTrigger> : null}
          </TabsList>
          <TabsContent value="transactions" className="mt-4">
            {register.length ? <TxnTable rows={register} running /> : <EmptyState title="Nothing here yet" />}
          </TabsContent>
          {feed ? (
            <TabsContent value="statements" className="mt-4">
              <ul className="divide-y rounded-xl border" aria-label="Statements">
                {statements.map((st) => (
                  <li key={st.import_id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 text-sm">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{st.file_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {st.period_start ? `${shortDate(st.period_start)} – ` : "To "}
                        {shortDate(st.period_end)} · {st.rows_inserted} rows
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      {st.balance_as_of ? (
                        st.assertion_ok ? (
                          <span className="text-xs text-emerald-700 dark:text-emerald-400">✓ Balance matches</span>
                        ) : (
                          <span className="text-xs text-destructive">Balance off by {st.difference?.formatted}</span>
                        )
                      ) : null}
                      <RemoveStatement statement={st} />
                    </div>
                  </li>
                ))}
              </ul>
            </TabsContent>
          ) : null}
        </Tabs>
      )}

      <UploadDialog
        accountId={account.id}
        accountName={account.name}
        open={uploading}
        onOpenChange={(open) => {
          setUploading(open);
          if (!open && params.get("upload")) router.replace(`/accounts/${id}`);
        }}
        onUploaded={refresh}
      />
      <ValueDialog accountId={account.id} open={valuing} onOpenChange={setValuing} onSaved={refresh} />
    </div>
  );
}

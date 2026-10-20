"use client";

import { useState } from "react";
import { ErrorNote, Loading, PageHeader } from "@/components/common/shared";
import { Panel } from "@/components/common/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, toPaise, type Settings } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useAction, useApi } from "@/lib/use-api";
import { PrivacyCard } from "./privacy";

const rupees = (paise: number | undefined) => (paise === undefined ? "" : String(paise / 100));

function SpendingSettings({ settings }: { settings: Settings }) {
  const { refresh } = usePerson();
  const [base, setBase] = useState(rupees(settings.min_cash_buffer.paise));
  const [allowance, setAllowance] = useState(rupees(settings.monthly_allowance?.paise));
  const [saved, setSaved] = useState(false);
  const { run, error, busy } = useAction(refresh);
  const basePaise = toPaise(base || "0");
  const allowancePaise = allowance.trim() ? toPaise(allowance) : null;
  const valid = basePaise !== null && (allowance.trim() === "" || allowancePaise !== null);

  return (
    <Panel title="Safe to spend">
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={async (e) => {
          e.preventDefault();
          setSaved(false);
          const done = await run(() =>
            api.patch("/settings", { min_cash_buffer_paise: basePaise, monthly_allowance_paise: allowancePaise }),
          );
          if (done !== undefined) setSaved(true);
        }}
      >
        <div className="space-y-1">
          <Label htmlFor="base-amount">Base amount kept aside ₹</Label>
          <Input id="base-amount" inputMode="decimal" value={base} onChange={(e) => setBase(e.target.value)} />
          <p className="text-xs text-muted-foreground">Never counted as spendable: an emergency cushion.</p>
        </div>
        <div className="space-y-1">
          <Label htmlFor="monthly-allowance">Monthly allowance ₹</Label>
          <Input id="monthly-allowance" inputMode="decimal" placeholder="No limit" value={allowance} onChange={(e) => setAllowance(e.target.value)} />
          <p className="text-xs text-muted-foreground">The most you mean to spend in a month. Leave empty for no limit.</p>
        </div>
        <ErrorNote message={error} />
        <div className="flex items-center gap-3 sm:col-span-2">
          <Button type="submit" disabled={!valid || busy}>Save</Button>
          {saved ? <span className="text-sm text-muted-foreground" role="status">Saved</span> : null}
        </div>
      </form>
    </Panel>
  );
}

export function SettingsPage() {
  const { version, refresh } = usePerson();
  const settings = useApi<Settings>("/settings", version);
  return (
    <div>
      <PageHeader title="Settings" />
      <div className="space-y-4">
        {settings.data ? <SpendingSettings key={settings.data.setup_completed_at ?? "s"} settings={settings.data} /> : <Loading what="settings" />}
        <PrivacyCard version={version} refresh={refresh} />
        <Panel title="Start over">
          <p className="text-sm text-muted-foreground">
            To delete every ledger on this machine, stop the app and run <code className="rounded bg-muted px-1">make reset</code>.
            Back up first with <code className="rounded bg-muted px-1">make backup</code>.
          </p>
        </Panel>
      </div>
    </div>
  );
}

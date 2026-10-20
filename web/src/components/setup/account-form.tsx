"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorNote, NativeSelect } from "@/components/common/shared";
import { api, toPaise, type Account, type AccountType, type Catalog } from "@/lib/api";
import { useAction } from "@/lib/use-api";

const OTHER = "Other";

/** Type, institution and name: what the owner says about an account. Accounts with no statement
 * format take their current value instead. */
export function AccountForm({ catalog, onAdded }: { catalog: Catalog; onAdded: (a: Account) => void }) {
  const [type, setType] = useState<AccountType>("savings");
  const [institution, setInstitution] = useState(catalog.institutions[0]?.name ?? OTHER);
  const [otherName, setOtherName] = useState("");
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const { run, error, busy } = useAction(() => {});

  const typeInfo = catalog.types.find((t) => t.type === type);
  const leaf = useMemo(
    () => catalog.institutions.find((i) => i.name === institution)?.accounts.find((a) => a.type === type),
    [catalog, institution, type],
  );
  const byHand = !leaf?.statements;
  const realInstitution = institution === OTHER ? otherName.trim() : institution;
  const suggested = `${realInstitution || "My"} ${typeInfo?.label ?? ""}`.trim();

  return (
    <form
      aria-label="Add an account"
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault();
        const paise = value ? toPaise(value) : null;
        const added = await run(() =>
          api.post<Account>("/accounts", {
            type,
            institution: realInstitution,
            name: name.trim() || suggested,
            ...(byHand && paise !== null ? { opening_value_paise: paise, opening_date: asOf } : {}),
          }),
        );
        if (added) {
          setName("");
          setValue("");
          onAdded(added);
        }
      }}
    >
      <div className="space-y-1">
        <Label htmlFor="account-type">Type</Label>
        <NativeSelect id="account-type" className="w-full" value={type} onChange={(e) => setType(e.target.value as AccountType)}>
          {catalog.types.map((t) => (
            <option key={t.type} value={t.type}>
              {t.label}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div className="space-y-1">
        <Label htmlFor="account-institution">Bank or provider</Label>
        <NativeSelect id="account-institution" className="w-full" value={institution} onChange={(e) => setInstitution(e.target.value)}>
          {catalog.institutions.map((i) => (
            <option key={i.name} value={i.name}>
              {i.name === OTHER ? "Something else" : i.name}
            </option>
          ))}
        </NativeSelect>
      </div>
      {institution === OTHER ? (
        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="account-other">Name of the bank or provider</Label>
          <Input id="account-other" required value={otherName} onChange={(e) => setOtherName(e.target.value)} />
        </div>
      ) : null}
      <div className="space-y-1 sm:col-span-2">
        <Label htmlFor="account-name">Name</Label>
        <Input id="account-name" placeholder={suggested} value={name} onChange={(e) => setName(e.target.value)} />
        <p className="text-xs text-muted-foreground">{leaf?.hint}</p>
      </div>
      {byHand ? (
        <>
          <div className="space-y-1">
            <Label htmlFor="account-value">Current value ₹{typeInfo?.manual ? "" : " (optional)"}</Label>
            <Input id="account-value" inputMode="decimal" required={typeInfo?.manual} value={value} onChange={(e) => setValue(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="account-asof">As of</Label>
            <Input id="account-asof" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </div>
        </>
      ) : null}
      <ErrorNote message={error} />
      <div className="sm:col-span-2">
        <Button type="submit" disabled={busy || (institution === OTHER && !otherName.trim())}>
          Add account
        </Button>
      </div>
    </form>
  );
}

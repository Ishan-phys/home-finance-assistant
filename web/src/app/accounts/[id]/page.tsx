import { Suspense } from "react";
import { AccountView } from "@/components/accounts/account-view";

export default async function AccountPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense>
      <AccountView id={id} />
    </Suspense>
  );
}

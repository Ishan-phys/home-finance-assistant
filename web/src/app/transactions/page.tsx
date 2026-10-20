import { Suspense } from "react";
import { TransactionsPage } from "@/components/transactions/transactions-page";

export default function Transactions() {
  return (
    <Suspense>
      <TransactionsPage />
    </Suspense>
  );
}

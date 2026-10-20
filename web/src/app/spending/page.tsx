import { Suspense } from "react";
import { SpendingPage } from "@/components/spending/spending";

export default function Spending() {
  return (
    <Suspense>
      <SpendingPage />
    </Suspense>
  );
}

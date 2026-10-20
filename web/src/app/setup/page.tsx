import { Suspense } from "react";
import { SetupWizard } from "@/components/setup/wizard";

export default function SetupPage() {
  return (
    <Suspense>
      <SetupWizard />
    </Suspense>
  );
}

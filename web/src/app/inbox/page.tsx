"use client";

import { PageHeader } from "@/components/common/shared";
import { InboxList } from "@/components/inbox/inbox-list";

export default function InboxPage() {
  return (
    <div>
      <PageHeader title="Inbox" subtitle="Everything that needs you, with the fix next to it. The goal is an empty list." />
      <InboxList />
    </div>
  );
}

"use client";

import { PageHeader } from "@/components/common/shared";
import { InboxList } from "@/components/inbox/inbox-list";

export default function InboxPage() {
  return (
    <div>
      <PageHeader title="Inbox" 
        subtitle="Everything that needs you, with the fix next to it. The goal is an empty list."
        about={{
          id: "inbox",
          summary: "Things the app could not settle on its own. Clearing them keeps your numbers right.",
          points: [
            "Typical items: a transaction with no category, a card payment waiting for the other account's statement, a card bill that is due, or a balance that does not match its statement.",
            "Money that left your bank for a credit card has a Pay a card button. Pick the card and it owes that much less straight away; you can undo it for 45 seconds, and the card's statement takes over when you upload it.",
            "A card bill you paid in part stays here with what is still due.",
            "Each item has its fix beside it. When the list is empty, your books are consistent.",
          ],
        }}
      />
      <InboxList />
    </div>
  );
}

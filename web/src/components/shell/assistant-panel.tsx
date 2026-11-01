"use client";

import { X } from "lucide-react";
import { PageGuide } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import { ChatPanel } from "./chat";

/** The assistant slides over from the right, so the page stays visible beside it. */
export function AssistantPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <aside
      aria-label="Assistant"
      aria-hidden={!open}
      className={`fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l bg-background shadow-xl transition-transform duration-200 sm:w-[420px] ${
        open ? "translate-x-0" : "pointer-events-none translate-x-full"
      }`}
    >
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="font-medium">Ask about your money</p>
          <p className="text-xs text-muted-foreground">Answers quote figures from your ledger.</p>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Close assistant" onClick={onClose}>
          <X />
        </Button>
      </div>
      <PageGuide
        title="About this assistant"
        className="rounded-none border-x-0 border-t-0 px-4 text-xs"
        about={{
          id: "assistant",
          points: [
            "Ask in plain words, for example “How much did I spend on food in September?”",
            "It looks up your ledger with tools. The small “checked …” tags show what it looked at.",
            "Every figure is calculated by the app, not by the model, so it matches the other pages.",
            "It explains your numbers but does not change them. To fix a category or add a rule, use the Transactions and Rules pages.",
          ],
        }}
      />
      <div className="min-h-0 flex-1 p-4">{open ? <ChatPanel /> : null}</div>
    </aside>
  );
}

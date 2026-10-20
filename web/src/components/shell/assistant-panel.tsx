"use client";

import { X } from "lucide-react";
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
      <div className="min-h-0 flex-1 p-4">{open ? <ChatPanel /> : null}</div>
    </aside>
  );
}

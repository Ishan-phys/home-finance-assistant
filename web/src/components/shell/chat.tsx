"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { personPath } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  text: string;
  tools?: string[];
}

const SUGGESTIONS = [
  "How much can I safely spend this month?",
  "Where did my money leak this month?",
  "What is my net worth, and what do I owe?",
];

/** The assistant's conversation. Figures come from tools over the ledger, never the model. */
export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const session = useRef<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setBusy(true);
    setDraft("");
    setMessages((m) => [...m, { role: "user", text }, { role: "assistant", text: "", tools: [] }]);
    const patch = (fn: (last: Message) => Message) =>
      setMessages((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);
    try {
      const res = await fetch(`/api${personPath("/chat")}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: session.current }),
      });
      if (!res.ok || !res.body) throw new Error("The assistant is unavailable.");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          if (!frame.startsWith("data: ")) continue;
          const event = JSON.parse(frame.slice(6));
          if (event.type === "session") session.current = event.session_id;
          else if (event.type === "tool") patch((l) => ({ ...l, tools: [...(l.tools ?? []), event.name] }));
          else if (event.type === "text") patch((l) => ({ ...l, text: l.text ? `${l.text}\n${event.text}` : event.text }));
          else if (event.type === "error") patch((l) => ({ ...l, text: event.message }));
        }
      }
    } catch (e) {
      patch((l) => ({ ...l, text: e instanceof Error ? e.message : "Something went wrong." }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div aria-label="Chat" className="flex h-full min-h-0 flex-col gap-3">
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1" data-testid="chat-log">
          {messages.length === 0 ? (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Figures come from the ledger, not from the model.</p>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void send(s)}
                  className="block w-full rounded-lg border px-3 py-2 text-left text-sm hover:bg-muted"
                >
                  {s}
                </button>
              ))}
            </div>
          ) : null}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "ml-8 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground" : "mr-4 space-y-1"}>
              {m.role === "assistant" && m.tools?.length ? (
                <div className="flex flex-wrap gap-1">
                  {m.tools.map((t, j) => (
                    <span key={j} className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                      checked {t.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              ) : null}
              <p className="whitespace-pre-wrap text-sm">{m.text || (m.role === "assistant" && busy ? "Thinking…" : "")}</p>
            </div>
          ))}
          <div ref={bottom} />
        </div>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send(draft);
          }}
        >
          <Input aria-label="Message" placeholder="Ask about your money" value={draft} onChange={(e) => setDraft(e.target.value)} />
          <Button type="submit" disabled={busy || !draft.trim()}>
            Send
          </Button>
        </form>
    </div>
  );
}

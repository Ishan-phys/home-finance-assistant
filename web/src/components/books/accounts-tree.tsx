"use client";

import Link from "next/link";
import { Amount, ErrorNote, Loading, PageHeader } from "@/components/common/shared";
import { Button } from "@/components/ui/button";
import type { AccountsTree, TreeNode } from "@/lib/api";
import { usePerson } from "@/lib/person";
import { useApi } from "@/lib/use-api";

function Nodes({ nodes, depth = 0 }: { nodes: TreeNode[]; depth?: number }) {
  return (
    <ul>
      {nodes.map((n) => (
        <li key={n.path}>
          <details open={depth < 1} className="group">
            <summary className="flex cursor-pointer list-none items-baseline justify-between gap-3 rounded px-2 py-1 text-sm hover:bg-muted/50" style={{ paddingLeft: `${0.5 + depth * 1}rem` }}>
              <span>
                {n.children.length ? <span className="mr-1 inline-block text-muted-foreground group-open:rotate-90">›</span> : <span className="mr-1 inline-block w-2" />}
                {n.account_id ? n.name : n.name.replace(/-/g, " ")}
                <span className="ml-2 font-mono text-[11px] text-muted-foreground">{n.path}</span>
              </span>
              <Amount value={n.balance} />
            </summary>
            {n.children.length ? <Nodes nodes={n.children} depth={depth + 1} /> : null}
          </details>
        </li>
      ))}
    </ul>
  );
}

/** The books in real accounting terms. Balance-sheet accounts show what they hold; income and
 * expense accounts show this month. Signs are the bookkeeping ones: liabilities, income and
 * equity are negative when they grow. */
export function AccountsTreePage() {
  const { version } = usePerson();
  const tree = useApi<AccountsTree>("/accounts/tree", version);
  if (!tree.data) return tree.error ? <ErrorNote message={tree.error} /> : <Loading what="accounts" />;
  return (
    <div>
      <PageHeader
        title="All accounts"
        subtitle="Your books in accounting terms. Every transaction moves money between these and adds up to zero. Investments are shown at cost here; their market value is on the Overview."
        action={<Button render={<Link href="/setup?step=accounts" />}>＋ Add account</Button>}
      />
      <div className="space-y-4">
        {tree.data.kinds.map((k) => (
          <section key={k.kind} aria-label={k.label} className="rounded-xl border p-3">
            <div className="mb-1 flex items-baseline justify-between px-2">
              <h2 className="font-medium">{k.label}</h2>
              <Amount value={k.total} className="text-sm text-muted-foreground" />
            </div>
            {k.nodes.length ? <Nodes nodes={k.nodes} /> : <p className="px-2 text-sm text-muted-foreground">Nothing yet</p>}
          </section>
        ))}
      </div>
    </div>
  );
}

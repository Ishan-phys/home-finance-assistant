"use client";

import type { ElementType } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

/** Each element is styled here because the app has no typography plugin, and the assistant's
 * answers should read like a short briefing: tight paragraphs, real lists, tables that scroll
 * sideways instead of breaking the panel. Raw HTML in the text is not rendered (react-markdown
 * drops it), so a model reply can never inject markup, and unsafe link schemes are removed. */
function styled(Tag: ElementType, base: string, extra: Record<string, unknown> = {}) {
  return function Styled(props: { node?: unknown; className?: string }) {
    // react-markdown passes the syntax-tree node along; it must not reach the DOM.
    const rest: Record<string, unknown> = { ...props };
    delete rest.node;
    delete rest.className;
    return <Tag className={cn(base, props.className)} {...extra} {...rest} />;
  };
}

const components: Components = {
  p: styled("p", "leading-relaxed"),
  strong: styled("strong", "font-semibold text-foreground"),
  em: styled("em", "italic"),
  ul: styled("ul", "list-disc space-y-1 pl-5 marker:text-muted-foreground"),
  ol: styled("ol", "list-decimal space-y-1 pl-5 marker:text-muted-foreground"),
  li: styled("li", "pl-0.5 leading-relaxed"),
  a: styled("a", "font-medium text-primary underline underline-offset-2", { target: "_blank", rel: "noopener noreferrer" }),
  // Headings are not asked for, but a model may still write them: keep them modest.
  h1: styled("p", "font-heading text-base font-medium"),
  h2: styled("p", "font-heading text-base font-medium"),
  h3: styled("p", "font-semibold"),
  h4: styled("p", "font-semibold"),
  blockquote: styled("blockquote", "border-l-2 border-primary/40 pl-3 text-muted-foreground"),
  hr: styled("hr", "my-1 border-border"),
  code: styled("code", "rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]"),
  pre: styled("pre", "overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs [&_code]:bg-transparent [&_code]:p-0"),
  table: function Table(props: { node?: unknown }) {
    const rest: Record<string, unknown> = { ...props };
    delete rest.node;
    return (
      <div className="-mx-1 overflow-x-auto rounded-lg border">
        <table className="w-full border-collapse text-left text-[0.8125rem]" {...rest} />
      </div>
    );
  },
  thead: styled("thead", "bg-muted/60 text-muted-foreground"),
  th: styled("th", "whitespace-nowrap px-2.5 py-1.5 font-medium"),
  td: styled("td", "whitespace-nowrap border-t px-2.5 py-1.5 tabular-nums"),
};

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("space-y-2.5 break-words text-sm", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

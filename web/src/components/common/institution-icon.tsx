import {
  Banknote,
  Building2,
  Coins,
  CreditCard,
  HandCoins,
  Landmark,
  PiggyBank,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import type { AccountType } from "@/lib/api";
import { brandFor } from "@/lib/institutions";
import { cn } from "@/lib/utils";

const SIZES = {
  xs: { box: "size-5 rounded-md", glyph: "size-3", mark: "text-[9px]", markLong: "text-[6px]" },
  sm: { box: "size-6 rounded-md", glyph: "size-3.5", mark: "text-[11px]", markLong: "text-[7px]" },
  md: { box: "size-8 rounded-lg", glyph: "size-4", mark: "text-sm", markLong: "text-[10px]" },
  lg: { box: "size-11 rounded-xl", glyph: "size-5", mark: "text-xl", markLong: "text-sm" },
} as const;

// What an account of this type looks like when its institution has no badge of its own.
const GLYPHS: Record<AccountType, LucideIcon> = {
  savings: Landmark,
  current: Landmark,
  cash: Banknote,
  credit_card: CreditCard,
  loan: HandCoins,
  fixed_deposit: PiggyBank,
  recurring_deposit: PiggyBank,
  mutual_fund: TrendingUp,
  stock: TrendingUp,
  property: Building2,
  gold: Coins,
};

/** A small badge for the bank or provider behind an account: a coloured monogram for the ones the
 * app knows (HDFC Bank, SBI, Axis Bank, Groww), otherwise an icon for the kind of account. It is
 * decoration only: the account's name always sits beside it, so it is hidden from screen readers.
 * The monogram is drawn by CSS, so it is not part of the page's text. */
export function InstitutionIcon({
  institution,
  type,
  size = "sm",
  className,
}: {
  institution?: string | null;
  type?: AccountType | null;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const s = SIZES[size];
  const brand = brandFor(institution);
  if (brand) {
    const mark = size === "xs" || size === "sm" ? brand.short : brand.mark;
    return (
      <span
        aria-hidden
        data-mark={mark}
        data-testid="institution-icon"
        data-institution={brand.key}
        style={{ backgroundColor: brand.colour }}
        className={cn(
          "inline-flex shrink-0 select-none items-center justify-center font-semibold leading-none tracking-tight text-white",
          "before:content-[attr(data-mark)]",
          s.box,
          mark.length > 1 ? s.markLong : s.mark,
          className,
        )}
      />
    );
  }
  const Glyph = (type && GLYPHS[type]) || Landmark;
  return (
    <span
      aria-hidden
      data-testid="institution-icon"
      data-institution="other"
      className={cn("inline-flex shrink-0 items-center justify-center bg-muted text-muted-foreground", s.box, className)}
    >
      <Glyph className={s.glyph} />
    </span>
  );
}

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
  xs: { box: "size-5 rounded-md", glyph: "size-3" },
  sm: { box: "size-6 rounded-md", glyph: "size-3.5" },
  md: { box: "size-8 rounded-lg", glyph: "size-4" },
  lg: { box: "size-11 rounded-xl", glyph: "size-5" },
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

/** A small badge for the bank or provider behind an account: its logo for the ones the app knows
 * (HDFC Bank, SBI, Axis Bank, Groww), otherwise an icon for the kind of account. It is decoration
 * only: the account's name always sits beside it, so it is hidden from screen readers and carries
 * no alt text. The logo sits on a white tile in both light and dark themes. */
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
    return (
      <span
        aria-hidden
        data-testid="institution-icon"
        data-institution={brand.key}
        className={cn("inline-flex shrink-0 items-center justify-center overflow-hidden bg-white ring-1 ring-border", s.box, className)}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- a tiny static logo, no optimisation needed */}
        <img src={brand.image} alt="" className="size-full object-contain" />
      </span>
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

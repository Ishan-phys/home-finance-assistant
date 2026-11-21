/** The banks and providers the app knows by name, for the small badge shown beside an account.
 * These are plain monograms in a brand colour, not the companies' logos. Anything else falls back
 * to an icon for the kind of account. */

export interface Brand {
  key: string;
  /** What a screen reader hears if the badge is ever read: the badge itself is decorative. */
  label: string;
  /** One to three letters drawn on the badge. */
  mark: string;
  /** A single letter for badges too small to read three. */
  short: string;
  /** Background colour. The mark is always white. */
  colour: string;
}

const BRANDS: Brand[] = [
  { key: "hdfc", label: "HDFC Bank", mark: "H", short: "H", colour: "#004c8f" },
  { key: "sbi", label: "State Bank of India", mark: "SBI", short: "S", colour: "#1f4e9c" },
  { key: "axis", label: "Axis Bank", mark: "A", short: "A", colour: "#97144d" },
  { key: "groww", label: "Groww", mark: "G", short: "G", colour: "#00a67e" },
];

// What an owner might have typed or picked, lower-cased and trimmed, mapped to a brand.
const ALIASES: Record<string, string> = {
  "hdfc bank": "hdfc",
  hdfc: "hdfc",
  sbi: "sbi",
  "state bank of india": "sbi",
  "axis bank": "axis",
  axis: "axis",
  groww: "groww",
};

/** The brand for an institution name, or null when it is not one the app knows. */
export function brandFor(institution: string | null | undefined): Brand | null {
  // The books name a bank's group after its path ("HDFC-Bank"), so hyphens count as spaces.
  const key = ALIASES[(institution ?? "").trim().toLowerCase().replace(/[-_]+/g, " ")];
  return BRANDS.find((b) => b.key === key) ?? null;
}

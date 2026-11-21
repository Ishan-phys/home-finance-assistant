/** The banks and providers the app knows by name, for the small logo shown beside an account.
 *
 * Each logo is an image file under `public/institutions/`, trimmed and centred on a square white
 * canvas. The logos are trademarks of their owners and appear only to show which bank or provider
 * an account is with. To add a bank, put its logo there and add a row below and an alias or two. */

export interface Brand {
  key: string;
  /** What a screen reader would hear if the badge were ever read: the badge itself is decorative. */
  label: string;
  /** The logo file, served from `public/`. */
  image: string;
}

const BRANDS: Brand[] = [
  { key: "hdfc", label: "HDFC Bank", image: "/institutions/hdfc.png" },
  { key: "sbi", label: "State Bank of India", image: "/institutions/sbi.png" },
  { key: "axis", label: "Axis Bank", image: "/institutions/axis.png" },
  { key: "groww", label: "Groww", image: "/institutions/groww.png" },
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

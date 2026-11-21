/** The banks and providers the app knows by name, for the small badge shown beside an account.
 *
 * A brand can show, in order of preference:
 *   - `glyph`: its mark as an SVG path, drawn white on a tile in its brand colour;
 *   - `image`: a full-colour logo file under `public/`, shown on a white tile;
 *   - otherwise a monogram (a letter or two) in its brand colour.
 *
 * The glyphs for HDFC Bank and Axis Bank are the marks from the Simple Icons project
 * (https://simpleicons.org, version 16.38.0, CC0), with its brand colours. The marks themselves are
 * trademarks of their owners and are used here only to show which bank an account is with. SBI and
 * Groww are not in Simple Icons, so they show a monogram until a logo file is added: put it in
 * `web/public/institutions/` and set `image` on the brand below. */

export interface Brand {
  key: string;
  /** What a screen reader hears if the badge is ever read: the badge itself is decorative. */
  label: string;
  /** One to three letters drawn when there is no logo. */
  mark: string;
  /** A single letter for monogram badges too small to read three. */
  short: string;
  /** Background colour of the tile. */
  colour: string;
  /** The mark as the `d` of a single SVG path in a 24 by 24 box. */
  glyph?: string;
  /** A full-colour logo file, such as "/institutions/sbi.svg". */
  image?: string;
}

const BRANDS: Brand[] = [
  {
    key: "hdfc",
    label: "HDFC Bank",
    mark: "H",
    short: "H",
    colour: "#004b8d",
    glyph:
      "M.572 0v10.842h3.712V4.485h6.381V0Zm12.413 0v4.485h6.383v6.357h4.06V0Zm-4.64 8.53v6.938h6.963V8.53ZM.572 13.153V24h10.093v-4.486h-6.38v-6.361zm18.796 0v6.361h-6.383V24h10.443V13.153Z",
  },
  { key: "sbi", label: "State Bank of India", mark: "SBI", short: "S", colour: "#1f4e9c" },
  {
    key: "axis",
    label: "Axis Bank",
    mark: "A",
    short: "A",
    colour: "#971a4d",
    glyph: "M11.978 1.596 0 22.404h7.453l8.265-14.369Zm.027 12.896 4.533 7.903H24l-4.533-7.903z",
  },
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

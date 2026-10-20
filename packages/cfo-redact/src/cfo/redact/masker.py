"""Local masking before every model call (spec 9.1).

Narrations are masked in this order:
  1. the owner's own redaction terms (their name, family names) -> [REDACTED]
  2. a virtual payment address (local@psp) -> [REDACTED]
  3. a run of six or more digits -> [REDACTED]
  4. any word on the bundled Indian given-name and surname list -> [REDACTED]

Account display names, institutions, account references, and rule titles become stable
aliases such as Liquid_Account_1 and Obligation_1. Amounts stay numeric. The alias map lives
in process memory and is applied back to the model's reply before the browser renders it.

Masking is best-effort: a name that is on neither list stays. The cockpit's privacy card shows
exactly what would be sent, and the owner can add terms.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from cfo.redact.names import NAMES

REDACTED = "[REDACTED]"

# Hyphens are narration separators (UPI-PAYEE-handle@psp), so a handle stops at one.
_VPA = re.compile(r"[A-Za-z0-9._]+@[A-Za-z][A-Za-z0-9]+")
_DIGITS = re.compile(r"\d{6,}")
_WORD = re.compile(r"[A-Za-z]{2,}")
_TOKEN_SPLIT = re.compile(r"(\[[A-Z_]+:[0-9a-f]+\])")


@dataclass(frozen=True, slots=True)
class AliasTarget:
    """One account's private strings, plus the alias family its display name belongs to
    (for example "Liquid_Account"). The caller knows what kind of account it is; the masker
    only numbers them."""

    key: str  # sort key: the numbering follows it, so the same ledger yields the same aliases
    name: str
    prefix: str
    institution: str | None = None
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class TitleTarget:
    """A rule title to alias, with the family ("Obligation", "Income_Source")."""

    key: str
    title: str
    prefix: str


@dataclass(slots=True)
class Masker:
    terms: tuple[str, ...] = ()
    aliases: dict[str, str] = field(default_factory=dict)  # real string -> alias
    _reverse: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        terms: Iterable[str] = (),
        accounts: Sequence[AliasTarget] = (),
        titles: Sequence[TitleTarget] = (),
    ) -> Masker:
        """Aliases are numbered by id order, so the same ledger always yields the same map."""
        aliases: dict[str, str] = {}
        counters: dict[str, int] = {}

        def assign(real: str | None, prefix: str) -> None:
            if not real or not real.strip() or real in aliases:
                return
            counters[prefix] = counters.get(prefix, 0) + 1
            aliases[real.strip()] = f"{prefix}_{counters[prefix]}"

        for a in sorted(accounts, key=lambda a: a.key):
            assign(a.name, a.prefix)
        for a in sorted(accounts, key=lambda a: a.key):
            assign(a.institution, "Institution")
            assign(a.reference, "Account_Reference")
        for t in sorted(titles, key=lambda t: (t.prefix, t.key)):
            assign(t.title, t.prefix)
        cleaned = tuple(t.strip() for t in terms if t and t.strip())
        m = cls(terms=cleaned, aliases=aliases)
        m._reverse = {alias: real for real, alias in aliases.items()}
        return m

    @classmethod
    def from_plain(
        cls,
        terms: Iterable[str] = (),
        accounts: Iterable[tuple[str, str, str, str | None, str | None]] = (),
        titles: Iterable[tuple[str, str, str]] = (),
    ) -> Masker:
        """Build from plain tuples: accounts as (key, name, family, institution, reference)
        and titles as (key, title, family). This is what a ledger hands over."""
        return cls.build(
            terms=terms,
            accounts=[AliasTarget(*a) for a in accounts],
            titles=[TitleTarget(*t) for t in titles],
        )

    # narrations ------------------------------------------------------------------

    def narration(self, text: str) -> str:
        """Mask one narration. Pseudonym tokens from the ingestion redactor pass through
        untouched, so the same payee keeps the same token end to end."""
        parts = _TOKEN_SPLIT.split(text)
        return "".join(p if i % 2 else self._mask_plain(p) for i, p in enumerate(parts))

    def _mask_plain(self, text: str) -> str:
        for term in sorted(self.terms, key=len, reverse=True):
            text = re.sub(re.escape(term), REDACTED, text, flags=re.IGNORECASE)
        text = _VPA.sub(REDACTED, text)
        text = _DIGITS.sub(REDACTED, text)
        return _WORD.sub(lambda m: REDACTED if m.group().lower() in NAMES else m.group(), text)

    # everything else: aliases, then narration masking ---------------------------------

    def text(self, text: str) -> str:
        """Alias known account and rule names, then mask the remainder like a narration."""
        for real in sorted(self.aliases, key=len, reverse=True):
            text = re.sub(re.escape(real), self.aliases[real], text, flags=re.IGNORECASE)
        return self.narration(text)

    def payload(self, value: Any) -> Any:
        """Mask every string inside a JSON-like structure. Numbers are left alone."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {k: self.payload(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.payload(v) for v in value]
        return value

    def unalias(self, text: str) -> str:
        """Put real names back into a reply before it reaches the browser."""
        for alias in sorted(self._reverse, key=len, reverse=True):
            text = re.sub(rf"\b{re.escape(alias)}\b", self._reverse[alias], text)
        return text

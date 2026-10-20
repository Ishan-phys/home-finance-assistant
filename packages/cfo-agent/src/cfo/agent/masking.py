"""The masker for a ledger: its stored private strings, turned into a redactor."""

from __future__ import annotations

from cfo.ledger.privacy import load_privacy_inputs
from cfo.redact.masker import Masker
from sqlalchemy.orm import Session


def build_masker(session: Session) -> Masker:
    return Masker.from_plain(**load_privacy_inputs(session))  # type: ignore[arg-type]

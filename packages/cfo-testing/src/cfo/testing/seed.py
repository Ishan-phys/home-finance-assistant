"""The checked-in merchant mappings as a model client."""

from __future__ import annotations

from cfo.categorize.seed import SeedClient as _Seed
from cfo.redact import Redactor, RedactorConfig
from cfo.testing import FIXTURE_DIR

_REDACTOR = Redactor(RedactorConfig(salt=b"seed-keys-are-matched-by-shape-0"))


def _stored_form(narration: str) -> str:
    """A seed narration as redaction stores it. Tokens differ by salt; `shape` ignores them."""
    return _REDACTOR.redact_text(narration)


class SeedClient(_Seed):
    def __init__(self) -> None:
        import json

        super().__init__(
            json.loads((FIXTURE_DIR / "merchant_mappings.json").read_text()), _stored_form
        )

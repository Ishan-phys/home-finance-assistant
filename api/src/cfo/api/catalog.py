"""What can be set up: the account types in plain words, and the institutions whose statements
the app reads. An account at an institution or of a type without a statement format is still
allowed: its value is entered by hand."""

from __future__ import annotations

from typing import Any

from cfo.core.types import AccountType
from cfo.parse.registry import ADAPTERS

Json = dict[str, Any]
T = AccountType

# institution -> type -> (binding, what to upload)
_INSTITUTIONS: dict[str, dict[AccountType, tuple[str, str]]] = {
    "HDFC Bank": {
        T.SAVINGS: ("hdfc_bank", "NetBanking account statement, .xls or .csv"),
        T.CURRENT: ("hdfc_bank", "NetBanking account statement, .xls or .csv"),
        T.CREDIT_CARD: ("hdfc_credit_card", "Billed card statement, .xls or .xlsx"),
    },
    "SBI": {
        T.SAVINGS: ("sbi_bank", "Account statement, .xlsx or .csv"),
        T.CURRENT: ("sbi_bank", "Account statement, .xlsx or .csv"),
    },
    "Axis Bank": {T.CREDIT_CARD: ("axis_credit_card", "Monthly card statement, PDF")},
    "Groww": {
        T.MUTUAL_FUND: ("groww", "Holdings statement or order history, .xlsx"),
        T.STOCK: ("groww", "Holdings statement or order history, .xlsx"),
    },
}
OTHER = "Other"


def resolve_binding(institution: str, type: AccountType) -> str | None:
    """The statement format for this institution and type, or None when there is none."""
    found = _INSTITUTIONS.get(institution, {}).get(type)
    return found[0] if found else None


def build_catalog() -> Json:
    types = [
        {
            "type": t.value,
            "label": t.label,
            "manual": t.manual,
            "group": t.group.value,
            "kind": t.kind.value,
        }
        for t in AccountType
    ]
    institutions = []
    for name, by_type in _INSTITUTIONS.items():
        accounts = []
        for t in AccountType:
            binding, hint = by_type.get(t, (None, ""))
            assert binding is None or binding in ADAPTERS
            accounts.append(
                {
                    "type": t.value,
                    "binding": binding,
                    "statements": binding is not None,
                    "hint": hint
                    or (
                        "You enter its value by hand"
                        if t.manual
                        else "No statement format yet: you enter its value by hand"
                    ),
                }
            )
        institutions.append({"name": name, "accounts": accounts})
    institutions.append(
        {
            "name": OTHER,
            "accounts": [
                {
                    "type": t.value,
                    "binding": None,
                    "statements": False,
                    "hint": "You enter its value by hand",
                }
                for t in AccountType
            ],
        }
    )
    return {"types": types, "institutions": institutions}

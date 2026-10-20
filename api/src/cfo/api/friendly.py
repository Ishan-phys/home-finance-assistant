"""Plain-language wording for failures the owner can act on.

The parsers and services raise precise, technical messages. They stay as `detail` for support;
what the cockpit shows is the `message` and `hint` written here."""

from __future__ import annotations

import re
from dataclasses import dataclass

# What to upload for each statement format.
EXPECTED = {
    "hdfc_bank": "the HDFC Bank account statement from NetBanking (.xls or .csv), with the columns Date, Narration, Withdrawals, Deposits and Closing Balance",
    "sbi_bank": "the SBI account statement (.xlsx or .csv) with Date, Description, Debit, Credit and Balance columns",
    "hdfc_credit_card": "the billed credit card statement from HDFC (.xls or .xlsx)",
    "axis_credit_card": "the monthly Axis credit card statement PDF",
    "groww": "the holdings statement or order history exported from Groww (.xlsx)",
}
LABEL = {
    "hdfc_bank": "HDFC Bank account",
    "sbi_bank": "SBI account",
    "hdfc_credit_card": "HDFC credit card",
    "axis_credit_card": "Axis credit card",
    "groww": "Groww",
}


@dataclass(frozen=True, slots=True)
class Friendly:
    message: str
    hint: str | None = None


_WRONG_FILE_HINT = (
    "Check that the file belongs to this account, or pick a different account to upload it to."
)


def _row_problem(reason: str) -> str:
    if "missing date" in reason:
        return "has no date"
    if "exactly one of debit or credit" in reason:
        return "should have either a debit or a credit amount, not both or neither"
    if "negative" in reason or "missing" in reason:
        return "has a missing or negative amount"
    if "unknown debit/credit marker" in reason:
        return "is not marked as a debit or a credit"
    if "unparseable date" in reason:
        return "has a date we can't read"
    if "unparseable amount" in reason:
        return "has an amount we can't read"
    return "can't be read"


def parse_failure(text: str) -> Friendly:
    if m := re.match(r"header not recognized for (\w+)(.*)", text):
        binding, rest = m.group(1), m.group(2)
        label = LABEL.get(binding, "this account")
        wanted = EXPECTED.get(binding)
        hint = f"Upload {wanted}, as downloaded and not edited." if wanted else _WRONG_FILE_HINT
        if "reads a PDF" in rest:
            return Friendly(f"{label} statements are PDFs, but this file is a spreadsheet.", hint)
        if "reads a spreadsheet" in rest:
            return Friendly(f"{label} statements are spreadsheets, but this file is a PDF.", hint)
        return Friendly(f"This file doesn't look like a {label} statement.", hint)
    if text.startswith("no usable date"):
        return Friendly(
            "We couldn't find any transactions in this file.",
            "Make sure the statement covers a period with activity, and that you downloaded the "
            "full statement rather than a summary.",
        )
    if text.startswith("unsupported extension"):
        return Friendly(
            "We can't read this kind of file.",
            "Upload a .csv, .xls or .xlsx file, or a PDF for Axis credit cards.",
        )
    if text.startswith("cannot read"):
        return Friendly(
            "We couldn't open this file.",
            "It may be damaged, or not the type its name says. Try downloading it again.",
        )
    if "no statement adapter" in text:
        return Friendly(
            "This account is tracked by hand, so there are no statements to upload.",
            "Add its balance from the Accounts tab instead.",
        )
    if text.startswith("no adapter is available"):
        return Friendly("We can't read statements for this kind of account yet.", None)
    if text.startswith("no holdings"):
        return Friendly(
            "This Groww file has no holdings in it.",
            "Export the holdings statement again once you hold something, or upload order history.",
        )
    return Friendly("We couldn't read this statement.", _WRONG_FILE_HINT)


def validation_failure(text: str) -> Friendly:
    if m := re.match(r"row (\d+): (.*)", text):
        return Friendly(
            f"Row {m.group(1)} of the statement {_row_problem(m.group(2))}.",
            "Open the file and check that row. Nothing was imported.",
        )
    if text.startswith("unparseable date"):
        d = re.search(r"'(.*)'", text)
        what = f" ({d.group(1)})" if d else ""
        return Friendly(
            f"A date in this file{what} isn't in a format we understand.",
            "Nothing was imported. Use the statement exactly as the bank provided it.",
        )
    if text.startswith("unparseable amount"):
        return Friendly(
            "An amount in this file isn't in a format we understand.",
            "Nothing was imported. Use the statement exactly as the bank provided it.",
        )
    if "larger than 10 MiB" in text:
        return Friendly("That file is too large.", "Statements up to 10 MB are accepted.")
    if "20,000" in text:
        return Friendly(
            "That file has too many rows.", "Upload a shorter period, up to 20,000 transactions."
        )
    return Friendly(text[:1].upper() + text[1:] if text else "That request wasn't valid.", None)


PASSWORD_REQUIRED = Friendly(
    "This file is password-protected.",
    "Enter its password to continue. Banks often use a mix of your name, date of birth or card digits.",
)
PASSWORD_INVALID = Friendly(
    "That password didn't open the file.",
    "Check it and try again. It isn't stored anywhere.",
)
REDACTION_FAILED = Friendly(
    "We couldn't safely hide the personal details in this file, so nothing was imported.",
    "Try again. If it keeps happening, quote the reference below.",
)
SETUP_REQUIRED = Friendly(
    "Add an account first",
    "Statements are added to an account. Create one in setup.",
)
CATEGORY_IN_USE = Friendly(
    "This category has transactions, so it cannot be deleted",
    "Merge it into another category instead.",
)
INTERNAL = Friendly(
    "Something went wrong on our side. Nothing was saved.",
    "Try again. If it keeps happening, quote the reference below.",
)

_FIELDS = {
    "display_name": "name",
    "cycle_day": "statement day",
    "amount_paise": "amount",
    "due_day": "due day",
    "due_date": "due date",
    "start_date": "start date",
    "min_cash_buffer_paise": "cash buffer",
}


def request_failure(where: str, msg: str) -> Friendly:
    field = _FIELDS.get(where.split(".")[-1], where.split(".")[-1].replace("_", " "))
    if "should have at least 1" in msg:
        return Friendly(f"Please fill in the {field}.", None)
    return Friendly(
        f"Please check the {field}: {msg[:1].lower() + msg[1:]}." if where else msg, None
    )

"""HDFC Bank and SBI account statement layouts."""

from cfo.parse.base import BankLayout, BankStatementAdapter

# Netbanking .xls: "Date | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. |
# Deposit Amt. | Closing Balance", a row of asterisks under the header, and dd/mm/yy dates.
# The alternate names cover the CSV variant of the same export.
HDFC_BANK = BankStatementAdapter(
    BankLayout(
        binding="hdfc_bank",
        date=("date", "txn date"),
        narration=("narration",),
        debit=("withdrawal amt.", "withdrawals", "withdrawal amount"),
        credit=("deposit amt.", "deposits", "deposit amount"),
        balance=("closing balance",),
    )
)

# .xlsx: "Date | Details | Ref No/Cheque No | Debit | Credit | Balance", dd/mm/yyyy dates,
# amounts as text, and narrations wrapped with an embedded newline.
SBI_BANK = BankStatementAdapter(
    BankLayout(
        binding="sbi_bank",
        date=("date",),
        narration=("details",),
        debit=("debit",),
        credit=("credit",),
        balance=("balance",),
    )
)

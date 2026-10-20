"""Regenerate the synthetic statement fixtures: `cd api && uv run python fixtures/build_fixtures.py`.

Each fixture copies an institution's layout (preamble, header, separators, footer) and holds
invented data only: no real names, account numbers, phone numbers, or UPI ids.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
import xlwt

OUT = Path(__file__).parent
OPENING = Decimal("100000.00")

# (date, narration, debit, credit)
HDFC_ROWS: list[tuple[date, str, str | None, str | None]] = [
    (date(2026, 9, 1), "NEFT CR-TESTCORP LTD-SALARY SEP-TEST USER-TESTN0001", None, "150000.00"),
    (date(2026, 9, 4), "CC 000000XXXXXX0001 BILLPAY PAYMENT", "16268.00", None),
    (date(2026, 9, 5), "NEFT DR-TEST LANDLORD-RENT SEP-TEST USER", "30000.00", None),
    (date(2026, 9, 7), "ACH D- TEST MUTUAL FUND SIP-REF0001", "10000.00", None),
    (date(2026, 9, 9), "UPI-TEST CAFE-TESTCAFE-REF000009-UPI", "250.00", None),
    (date(2026, 9, 9), "UPI-TEST CAFE-TESTCAFE-REF000009-UPI", "250.00", None),
    (date(2026, 9, 12), "UPI-TEST GROCER-TESTGROCER-REF000012-UPI", "1850.50", None),
    (date(2026, 9, 28), "UPIRET-TEST CAFE REFUND", None, "250.00"),
    (date(2026, 10, 1), "INTEREST PAID TILL 30-SEP-2026", None, "824.00"),
]

SBI_ROWS: list[tuple[date, str, str | None, str | None]] = [
    (
        date(2026, 9, 1),
        " WDL TFR   UPI/DR/000000000001/TEST SHOP/TEST/te\n st@/UPI   0000000000001 AT 00000 TEST BR",
        "105.00",
        None,
    ),
    (
        date(2026, 9, 3),
        " WDL TFR   UPI/DR/000000000002/TEST CAB/TEST/te\n st@/UPI   0000000000002 AT 00000 TEST BR",
        "304.00",
        None,
    ),
    (date(2026, 9, 20), " DEP TFR   0000000000003 OF TEST USER AT 00000 TEST BR", None, "5000.00"),
    (date(2026, 9, 25), " INTERES\n T CREDIT", None, "2573.00"),
]


def _running(rows: list[tuple[date, str, str | None, str | None]], opening: Decimal):
    bal = opening
    for d, narr, debit, credit in rows:
        bal += Decimal(credit or 0) - Decimal(debit or 0)
        yield d, narr, debit, credit, bal


def build_hdfc_xls() -> None:
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    pre = [
        "HDFC BANK Ltd.                  Page No .:  1",
        "",
        "",
        "",
        "TEST USER",
        "1 TEST ROAD",
        "TEST CITY",
        "TESTSTATE INDIA",
        "Statement From  :  01/09/2026         To  :  30/09/2026",
    ]
    r = 0
    for line in pre:
        ws.write(r, 0, line)
        r += 1
    ws.write(r, 0, "*" * 60)
    r += 1
    for c, h in enumerate(
        [
            "Date",
            "Narration",
            "Chq./Ref.No.",
            "Value Dt",
            "Withdrawal Amt.",
            "Deposit Amt.",
            "Closing Balance",
        ]
    ):
        ws.write(r, c, h)
    r += 1
    for c, w in enumerate([8, 34, 12, 8, 18, 18, 18]):
        ws.write(r, c, "*" * w)
    r += 1
    total_d = total_c = Decimal(0)
    for i, (d, narr, debit, credit, bal) in enumerate(_running(HDFC_ROWS, OPENING), start=1):
        ws.write(r, 0, d.strftime("%d/%m/%y"))
        ws.write(r, 1, narr)
        ws.write(r, 2, f"{i:016d}")
        ws.write(r, 3, d.strftime("%d/%m/%y"))
        if debit:
            ws.write(r, 4, float(debit))
            total_d += Decimal(debit)
        if credit:
            ws.write(r, 5, float(credit))
            total_c += Decimal(credit)
        ws.write(r, 6, float(bal))
        r += 1
    r += 1
    ws.write(r + 1, 0, "STATEMENT SUMMARY  :-")
    ws.write(r + 2, 0, "Opening Balance")
    ws.write(r + 3, 0, float(OPENING))
    ws.write(r + 3, 4, float(total_d))
    ws.write(r + 3, 5, float(total_c))
    ws.write(r + 3, 6, float(OPENING + total_c - total_d))
    wb.save(str(OUT / "hdfc_bank_sep.xls"))


def build_hdfc_csv() -> None:
    """The CSV variant: alternate header names, dd/mm/yyyy dates, Indian-grouped text."""
    with open(OUT / "hdfc_bank_sep.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Statement From : 01/09/2026 To : 30/09/2026"])
        w.writerow([])
        w.writerow(["Txn Date", "Narration", "Withdrawals", "Deposits", "Closing Balance"])
        for d, narr, debit, credit, bal in _running(HDFC_ROWS, OPENING):
            w.writerow(
                [d.strftime("%d/%m/%Y"), narr, _indian(debit), _indian(credit), _indian(str(bal))]
            )


def _indian(text: str | None) -> str:
    if text is None:
        return ""
    whole, _, frac = text.partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail]) + (f".{frac}" if frac else "")


def build_sbi_xlsx() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for _ in range(1):
        ws.append([None] * 6)
    ws.append(["SBI"])
    ws.append([None] * 6)
    ws.append(["Statement From  :  01-09-2026  to  30-09-2026"])
    ws.append(["Date", "Details", "Ref No/Cheque No", "Debit", "Credit", "Balance"])
    opening = Decimal("258017.40")
    total_d = total_c = Decimal(0)
    for d, narr, debit, credit, bal in _running(SBI_ROWS, opening):
        ws.append(
            [
                d.strftime("%d/%m/%Y"),
                narr,
                None,
                debit and f"{Decimal(debit):.2f}",
                credit and f"{Decimal(credit):.2f}",
                f"{bal:.2f}",
            ]
        )
        total_d += Decimal(debit or 0)
        total_c += Decimal(credit or 0)
    ws.append([None] * 6)
    ws.append(["Statement Summary : 01-09-2026  To  30-09-2026"])
    ws.append(
        [
            "Brought Forward (₹)",
            "Dr Count",
            "Cr Count",
            "Total Debits (₹)",
            "Total Credits (₹)",
            "Closing Balance (₹)",
        ]
    )
    ws.append(
        [
            f"{_indian(str(opening))}CR",
            2,
            2,
            _indian(f"{total_d:.2f}"),
            _indian(f"{total_c:.2f}"),
            f"{_indian(f'{opening + total_c - total_d:.2f}')}CR",
        ]
    )
    wb.save(OUT / "sbi_bank_sep.xlsx")


CARD_ROWS = [  # (date, time, description, amount, "Cr" or "")
    (date(2026, 8, 21), "21:25", "TEST FOOD ORDER CITY", "138.00", ""),
    (date(2026, 8, 24), "00:00", "10% TEST CASHBACK", "93.20", "Cr"),
    (date(2026, 9, 3), "19:20", "TEST FOOD ORDER CITY", "647.00", ""),
    (date(2026, 9, 3), "19:20", "TEST FOOD ORDER CITY", "647.00", ""),
    (
        date(2026, 9, 4),
        "17:10",
        "BPPY CC PAYMENT DP0000 TEST (Ref# ST26000000000000000)",
        "16,268.00",
        "Cr",
    ),
    (date(2026, 9, 12), "10:15", "TEST GROCER CITY", "1,250.50", ""),
]


def build_hdfc_card_xls() -> None:
    """Named .xlsx like the real export, but a legacy .xls workbook inside."""
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    ws.write(0, 0, "Name")
    ws.write(0, 4, "TEST USER")
    ws.write(2, 13, "Credit Card No.: 5200XXXXXX0001")
    ws.write(5, 0, "Payment Due Date")
    ws.write(5, 4, "10 Oct, 2026")
    ws.write(6, 0, "Statement Date")
    ws.write(6, 4, "20 Sep, 2026")
    ws.write(7, 0, "Total Amount Due")
    ws.write(7, 4, "10,064.00")
    ws.write(8, 0, "Minimum Amount Due")
    ws.write(8, 4, "510.00")
    ws.write(14, 0, "Opening Bal")
    ws.write(14, 5, "Payment / Credit")
    ws.write(14, 10, "Purchases / Debits")
    ws.write(14, 15, "Finance Charges")
    ws.write(14, 20, "Total Dues")
    ws.write(15, 0, "16,267.62")
    ws.write(15, 5, "16,361.20")
    ws.write(15, 10, "2,682.50")
    ws.write(15, 15, "0.00")
    ws.write(15, 20, "10,064.00")
    for c, h in {
        0: "Transaction type",
        4: "Primary / Addon Customer Name",
        9: "Date & Time",
        12: "Description",
        18: "REWARDS",
        20: "AMT",
        23: "Debit / Credit",
    }.items():
        ws.write(18, c, h)
    r = 19
    for d, t, desc, amt, dc in CARD_ROWS:
        ws.write(r, 0, "Domestic")
        ws.write(r, 4, "TEST USER")
        ws.write(r, 9, f"{d.strftime('%d/%m/%Y')} / {t}")
        ws.write(r, 12, desc + " ")
        ws.write(r, 20, amt)
        if dc:
            ws.write(r, 23, dc)
        r += 1
    ws.write(r + 1, 0, "Reward Points Summary")
    ws.write(r + 2, 0, "10% TEST CASHBACK")  # a later section must not be read as transactions
    wb.save(str(OUT / "hdfc_card_sep.xlsx"))


def build_groww_mf() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append([])
    ws.append(["Personal Details"])
    ws.append(["Name", "Test User"])
    ws.append([])
    ws.append(["HOLDING SUMMARY"])
    ws.append(["Total Investments", "Current Portfolio Value", "Profit/Loss"])
    ws.append([100000.0, 112000.5, 12000.5])
    ws.append([])
    ws.append(["HOLDINGS AS ON 2026-10-03"])
    ws.append([])
    ws.append(
        [
            "Scheme Name",
            "AMC",
            "Category",
            "Sub-category",
            "Folio No.",
            "Source",
            "Units",
            "Invested Value",
            "Current Value",
            "Returns",
            "XIRR",
        ]
    )
    ws.append([])
    ws.append(
        [
            "Test Index Fund Direct Growth",
            "Test MF",
            "Equity",
            "Large Cap",
            "F0001",
            "Groww",
            100.5,
            50000.0,
            62000.25,
            12000.25,
            "24%",
        ]
    )
    ws.append(
        [
            "Test Gold Fund Direct Growth",
            "Test MF",
            "Commodities",
            "Gold",
            "F0002",
            "Groww",
            10.0,
            50000.0,
            50000.25,
            0.250000000001,
            "0.1%",
        ]
    )  # float noise like the real export
    wb.save(OUT / "groww_mf_holdings.xlsx")


def build_groww_stocks() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Name", "Test User"])
    ws.append(["Unique Client Code", "T0001"])
    ws.append([])
    ws.append(["Holdings statement for stocks as on 02-10-2026"])
    ws.append([])
    ws.append(["Summary"])
    ws.append(["Invested Value", 86863.61])
    ws.append(["Closing Value", 85365.29])
    ws.append([])
    ws.append(
        [
            "Stock Name",
            "ISIN",
            "Quantity",
            "Average buy price",
            "Buy value",
            "Closing price",
            "Closing value",
            "Unrealised P&L",
        ]
    )
    ws.append(
        [
            "TEST ETF GOLD",
            "INF000000001",
            703.0,
            123.56,
            86862.68,
            121.43,
            85365.29000000001,
            -1497.39,
        ]
    )
    wb.save(OUT / "groww_stocks_holdings.xlsx")


AXIS_ROWS = [  # (date text, details, amount, Debit or Credit)
    ("08 Sep '26", "Cashback credit Aug26-POS:100", "100.00", "Credit"),
    ("05 Sep '26", "TEST ELECTRONICS,CITY", "1,500.00", "Debit"),
    ("03 Sep '26", "TEST FOODS PVT LTD,CITY", "250.00", "Debit"),
    ("03 Sep '26", "TEST FOODS PVT LTD,CITY", "250.00", "Debit"),
    ("30 Aug '26", "MB/IB PAYMENT #TEST0000000001", "3,000.00", "Credit"),
]


def axis_pdf_lines(
    opening: str, total_due: str, rows: list[tuple[str, str, str, str]]
) -> list[str]:
    return [
        "Axis Bank Test Credit Card Monthly Statement",
        "TEST USER",
        "1 TEST ROAD",
        "TEST CITY 000000 Credit Card Number: 5200XXXXXXXX0001",
        "Payment Summary",
        "Total Payment Due Minimum Payment Due Payment Due Date",
        f"₹ {total_due} ₹ 200.00 03 Oct '26",
        "Selected Statement Month Credit Limit Opening Balance",
        f"Sep 2026 ₹ 4,00,000.00 ₹ {opening}",
        "Transaction Summary",
        "Date Transaction Details Amount (INR) Debit/Credit",
        *[f"{d} {desc} ₹ {amt} {kind}" for d, desc, amt, kind in rows],
        "**End of Transaction Summary**",
    ]


def build_axis_pdf() -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(OUT / "axis_card_sep.pdf"), pagesize=A4)
    c.setFont("Helvetica", 9)
    y = 800
    for line in axis_pdf_lines("5,000.00", "3,900.00", AXIS_ROWS):
        c.drawString(40, y, line.replace("₹", "Rs"))  # Helvetica has no rupee glyph
        y -= 14
    c.save()


def build_axis_protected() -> None:
    """The Axis PDF again, AES-encrypted. The password is synthetic: fixture-pass."""
    import pikepdf

    with pikepdf.open(OUT / "axis_card_sep.pdf") as pdf:
        pdf.save(
            OUT / "axis_card_sep_protected.pdf",
            encryption=pikepdf.Encryption(user="fixture-pass", owner="fixture-owner", aes=True),
        )


def build_groww_orders() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for _ in range(2):
        ws.append([])
    ws.append(["Personal Details"])
    ws.append(["Name", "Test User"])
    ws.append([])
    ws.append([])
    ws.append([])
    ws.append([])
    ws.append(["TRANSACTIONS FROM Apr 01 2026 TO Oct 03 2026"])
    ws.append([])
    ws.append(["Scheme Name", "Transaction Type", "Units", "NAV", "Amount", "Date"])
    ws.append([])
    ws.append([])
    ws.append(
        ["Test Gold Fund Direct Growth", "PURCHASE", "109.26", "45.76", "4,999", "28 Sep 2026"]
    )
    ws.append(
        ["Test Flexi Cap Fund Direct Growth", "REDEEM", "559.91", "87.7", "49,106", "15 Sep 2026"]
    )
    ws.append(
        ["Test Gold Fund Direct Growth", "PURCHASE", "100.19", "49.9", "4,999", "26 Aug 2026"]
    )
    ws.append(
        ["Test Gold Fund Direct Growth", "PURCHASE", "100.19", "49.9", "4,999", "26 Aug 2026"]
    )
    wb.save(OUT / "groww_mf_orders.xlsx")


if __name__ == "__main__":
    build_axis_pdf()
    build_axis_protected()
    build_groww_orders()
    build_hdfc_card_xls()
    build_groww_mf()
    build_groww_stocks()
    build_hdfc_xls()
    build_hdfc_csv()
    build_sbi_xlsx()
    print("fixtures written to", OUT)

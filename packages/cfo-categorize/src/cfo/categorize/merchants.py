"""Derive a readable merchant name from a redacted narration, locally and by rule.

The Decisions API answers from fixed options and returns no free text, so the merchant is cleaned
here. The rules know the shape of UPI, IMPS/NEFT, SBI and HDFC card narrations; anything else
falls back to the first meaningful words, title-cased.
"""

from __future__ import annotations

import re

PERSONAL_TRANSFER = "Personal transfer"

_TOKEN = re.compile(r"\[[A-Z_]+(?::[0-9a-f]+)?\]")
_NOISE_PREFIX = re.compile(
    r"^(?:UPIRET|UPI|IMPS|NEFT|RTGS|ACH|NACH|POS|ATM|ECS|MB|IB|WDL TFR|DEP TFR|TFR|BPPY|CC|DR|CR)\b[-/ ]*",
    re.I,
)
_GATEWAY = re.compile(r"^[A-Z]{2,5}\*")  # PAY*, CAS*, PYU*, RSP*
_SKIP_SEGMENTS = {
    "AUTOPAY",
    "MANDATE",
    "COLLECT",
    "UPI",
    "DR",
    "CR",
    "PAYMENT",
    "PAY",
    "SI",
    "NA",
    "REVERSAL",
}
_TAIL_WORDS = re.compile(
    r"\b(?:PVT|PRIVATE|LTD|LIMITED|LLP|INC|CORP|SERVICES?|SOLUTIONS?|TECHNOLOGIES|ENTERPRISES?"
    r"|INDIA|FO|REFUND|REVERSAL)\b\.?",
    re.I,
)
_ACRONYMS = {
    "UPI",
    "HDFC",
    "SBI",
    "ICICI",
    "AXIS",
    "IMPS",
    "NEFT",
    "GST",
    "SIP",
    "ATM",
    "EMI",
    "IGST",
    "SMS",
}
_CITIES = {
    "bangalore",
    "bengaluru",
    "mumbai",
    "delhi",
    "gurgaon",
    "gurugram",
    "noida",
    "pune",
    "hyderabad",
    "chennai",
    "kolkata",
    "ahmedabad",
    "jaipur",
    "lucknow",
    "allahabad",
    "prayagraj",
    "kochi",
    "san",
    "francisc",
    "francisco",
    "online",
    "mum",
    "blr",
}


def _is_noise(segment: str) -> bool:
    s = segment.strip()
    return (
        not s
        or _TOKEN.fullmatch(s) is not None
        or bool(re.fullmatch(r"[\d\W_]+", s))
        or s.upper() in _SKIP_SEGMENTS
        or bool(re.fullmatch(r"[A-Z]{4}\d{3,}|[A-Z]{4}\[.*", s))  # an IFSC left over
        or bool(re.fullmatch(r"\(?ref#?.*", s, re.I))
    )


def _tidy(text: str) -> str:
    text = _TOKEN.sub(" ", text)
    text = _GATEWAY.sub("", text.strip())
    text = re.sub(r"\(.*?\)|#\S+|\bRef#?\S*", " ", text)
    text = re.sub(r"[^A-Za-z0-9&' .]", " ", text)
    text = _TAIL_WORDS.sub(" ", text)
    words = [w for w in text.split() if not re.fullmatch(r"\d+", w)]
    while len(words) > 1 and words[-1].lower() in _CITIES:
        words.pop()
    name = " ".join(words[:4]).strip(" .")
    return " ".join(w if w.upper() in _ACRONYMS else w.capitalize() for w in name.split())


def clean_merchant(description: str) -> str:
    """A merchant name, or the whole narration tidied when no rule applies."""
    text = description.strip()
    # UPI/DR/<ref>/<payee>/<bank>/...  (SBI) and UPI-<payee>-<handle>-... (HDFC)
    body = re.sub(r"^(?:WDL TFR|DEP TFR)\s+", "", text, flags=re.I)
    body = re.sub(r"^ACH\s+[DC]\s*-\s*", "", body, flags=re.I)
    if re.match(r"UPI(?:RET)?[/-]", body, re.I):
        segments = re.split(r"[/-]", body)[1:]
        for seg in segments:
            if not _is_noise(seg):
                name = _tidy(seg)
                if name:
                    return name
    elif re.match(r"(?:IMPS|NEFT|RTGS)[-/ ]", body, re.I):
        segments = re.split(r"[-/]", body)[1:]
        for seg in segments:
            if not _is_noise(seg) and seg.strip().upper() not in {"CR", "DR"}:
                name = _tidy(seg)
                if name:
                    return name
    elif re.match(r"POS\s", body, re.I):
        tail = re.sub(r"^POS\s+(?:\S+\s+){1,3}\d{2}[A-Z]{3}\d{2}\s+\d{2}:\d{2}:\d{2}\s+", "", body)
        name = _tidy(tail if tail != body else re.sub(r"^POS\s+", "", body))
        if name:
            return name
    name = _tidy(_NOISE_PREFIX.sub("", body))
    return name or _tidy(body) or "Unknown"

"""Unlock password-protected statements before parsing (spec iteration 2, pulled forward).

Banks protect PDFs and workbooks with a password the owner knows (often a date of birth or
a card-number fragment). The password arrives with the upload request, opens the file in
memory, and is never stored, logged, or echoed in an error. Adapters only ever see plaintext
bytes, so none of them knows about passwords.

Supported: encrypted PDFs (RC4 and AES), and Office-encrypted .xlsx. Legacy .xls with Office
encryption is handled by the same library but has no checked-in fixture to verify against.
"""

from __future__ import annotations

import io

import msoffcrypto
import pikepdf
from cfo.parse.base import ParseFailed, PasswordInvalid, PasswordRequired
from msoffcrypto.exceptions import DecryptionError, InvalidKeyError

_PDF = b"%PDF"
_OLE2 = b"\xd0\xcf\x11\xe0"
_ZIP = b"PK\x03\x04"


def unlock(content: bytes, password: str | None) -> bytes:
    """Return plaintext bytes. Unprotected files pass through untouched, with or without a
    password. Raises PasswordRequired or PasswordInvalid for a protected file."""
    if content.startswith(_PDF):
        return _unlock_pdf(content, password)
    if content.startswith(_OLE2):  # Office-encrypted workbooks are OLE2 containers
        return _unlock_office(content, password)
    return content


def _unlock_pdf(content: bytes, password: str | None) -> bytes:
    try:
        pdf = pikepdf.open(io.BytesIO(content), password=password or "")
    except pikepdf.PasswordError as exc:
        raise (
            PasswordInvalid("the password did not open the PDF")
            if password
            else PasswordRequired("the PDF is password-protected")
        ) from exc
    except pikepdf.PdfError as exc:
        raise ParseFailed("cannot read the PDF") from exc
    with pdf:
        if not pdf.is_encrypted:
            return content
        out = io.BytesIO()
        pdf.save(out)  # saved without encryption
        return out.getvalue()


def _unlock_office(content: bytes, password: str | None) -> bytes:
    try:
        office = msoffcrypto.OfficeFile(io.BytesIO(content))
        encrypted = office.is_encrypted()
    except Exception:  # a plain legacy .xls is OLE2 too; it is not encrypted
        return content
    if not encrypted:
        return content
    if not password:
        raise PasswordRequired("the workbook is password-protected")
    try:
        office.load_key(password=password)
        out = io.BytesIO()
        office.decrypt(out)
    except (InvalidKeyError, DecryptionError) as exc:
        raise PasswordInvalid("the password did not open the workbook") from exc
    except Exception as exc:
        raise ParseFailed("cannot read the protected workbook") from exc
    return out.getvalue()

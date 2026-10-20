"""The neutral form every statement file is read into.

A bank statement arrives as a PDF, a workbook, or a CSV. Everything downstream of reading,
redaction and parsing alike, works on a `Document` and never on file bytes. That is what lets
one redactor serve every format and lets adapters contain only layout knowledge.
"""

from cfo.doc.document import Document, DocumentKind

__all__ = ["Document", "DocumentKind"]

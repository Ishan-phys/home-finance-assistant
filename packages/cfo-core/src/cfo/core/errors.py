"""Expected failures raised by the ledger services. HTTP maps each to a 4xx code."""


class LedgerError(Exception):
    pass


class NotFoundError(LedgerError):
    """NOT_FOUND: unknown account, rule, instance, or transaction."""


class ConflictError(LedgerError):
    """CONFLICT: the request conflicts with current state."""


class RedactionFailed(Exception):
    """REDACTION_FAILED: personal details could not be redacted, so nothing was imported."""


class UnbalancedTransaction(LedgerError):
    """A transaction's postings do not sum to zero, or it has fewer than two."""


class SetupRequired(LedgerError):
    """The ledger has no account yet, so there is nothing to upload a statement onto."""


class InvalidInput(LedgerError):
    """INVALID_INPUT: the request is well-formed but the values cannot be used."""


class CategoryInUse(ConflictError):
    """CATEGORY_IN_USE: a category with transactions cannot be deleted; merge it instead."""

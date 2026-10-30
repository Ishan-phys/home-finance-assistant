"""The statement upload pipeline (spec 4.5, 4.12 and design §5.2–§5.5).

    unlock -> read -> redact -> parse -> categorize -> journal

Uploads run one at a time and only onto an account of a set-up ledger. The file exists only in
memory, and everything after the redact stage sees pseudonym tokens, never names or numbers.
Categorization runs before the database transaction opens, and the ledger write commits in one
transaction: rows become balanced transactions, own-account halves pair, and the statement's
closing balance becomes an assertion (or, for holdings, a valuation). The pipeline fails closed:
if redaction raises, the upload is rejected and no unredacted text is used.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from cfo.categorize.categorizer import ModelClient
from cfo.categorize.port import OWN_MOVE_LABEL, Categorizer, Item, Label, as_categorizer
from cfo.core.errors import NotFoundError, RedactionFailed, SetupRequired
from cfo.core.ids import Id
from cfo.core.types import (
    Account,
    AccountRole,
    AccountType,
    Direction,
    Group,
    MerchantMapping,
    Scope,
)
from cfo.doc import Document
from cfo.ingest.dedup import HashedRow, hash_rows
from cfo.ingest.examples import owner_examples
from cfo.ingest.masking import build_masker
from cfo.ledger.journal import (
    RowIn,
    account_gaps,
    pair_in_transit,
    post_rows,
    recompute_opening,
    record_assertion,
    revalue,
)
from cfo.ledger.repositories.accounts import (
    AccountRepository,
    ImportHashRepository,
    ImportRepository,
    RedactionTermRepository,
    SettingsRepository,
)
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.originals import OriginalRepository
from cfo.ledger.repositories.scope import ScopeMissingError
from cfo.ledger.repositories.transactions import JournalRepository, MappingRepository
from cfo.ledger.rules_service import active_rules, rule_mappings
from cfo.ledger.setup import is_set_up
from cfo.parse.base import ParsedStatement, ParseFailed
from cfo.parse.readers import read_document
from cfo.parse.registry import ADAPTERS, Adapter
from cfo.parse.unlock import unlock
from cfo.redact import RedactionError, RedactionReport, Redactor, RedactorConfig
from cfo.vault import Vault
from sqlalchemy.orm import Session

log = logging.getLogger("cfo.ingest")
_HOLDINGS_TYPE = {"mutual_funds": AccountType.MUTUAL_FUND, "stocks": AccountType.STOCK}


@dataclass(frozen=True, slots=True)
class UploadResult:
    import_id: Id
    rows_inserted: int
    hashes_ignored: int
    pairs_merged: int
    uncategorized: int
    gaps: int  # statement balances on this account the ledger does not agree with
    warnings: tuple[str, ...] = field(default_factory=tuple)
    redaction: dict[str, int] = field(default_factory=dict)  # counts per class, never values


def ledger_labels(s: Session) -> list[Label]:
    """The ledger's own active categories, as the categorizer is offered them."""
    labels = [
        Label(
            a.path,
            a.display_name,
            (a.description or a.display_name) + (f" Also: {a.keywords}." if a.keywords else ""),
            "credit" if a.direction is Direction.IN else "debit",
        )
        for a in AccountRepository(s).list_all(AccountRole.CATEGORY)
    ]
    return [*labels, OWN_MOVE_LABEL]


def _holdings_warning(account: Account, parsed: ParsedStatement) -> str | None:
    kind = _HOLDINGS_TYPE.get(parsed.holdings_kind or "")
    if kind is None or account.type is kind:
        return None
    what = parsed.holdings_kind.replace("_", " ")  # type: ignore[union-attr]
    return (
        f"this is a {what} file but {account.display_name} is a "
        f"{account.type.label.lower() if account.type else 'different'} account; each holdings "
        "type needs its own account so one upload does not replace the other's value"
    )


def upload_statement(
    db: Database,
    account_id: Id,
    filename: str,
    content: bytes,
    client: Categorizer | ModelClient | None,
    today: date,
    password: str | None = None,
    scope: Scope | None = None,
    vault: Vault | None = None,
) -> UploadResult:
    """Import one statement file onto an account.

    Raises SetupRequired before the ledger has an account, NotFoundError for an unknown
    account, and ParseFailed (PasswordRequired or PasswordInvalid for a protected file), or
    ValidationFailed for a file the adapter rejects; a rejected file writes nothing. `scope` is
    the person's ledger and bounds everything the upload reads and writes. With a `vault`, each
    row's original narration is kept sealed beside the redacted one, for the owner to read and for
    rules to match; it is never sent anywhere.
    """
    with db.upload_lock():
        scope = scope or db.default_scope
        if scope is None:
            raise ScopeMissingError("an upload needs the scope of the person it belongs to")
        with db.transaction(scope) as s:
            if not is_set_up(s):
                raise SetupRequired("add an account before uploading statements")
            account = AccountRepository(s).get(account_id)
            redactor = Redactor(
                RedactorConfig(
                    salt=SettingsRepository(s).salt(),
                    terms=tuple(RedactionTermRepository(s).list_all()),
                    card_statement=bool(account and account.binding and "card" in account.binding),
                )
            )
            labels = ledger_labels(s)
        if account is None or account.role is not AccountRole.REAL:
            raise NotFoundError(f"unknown account {account_id}")
        if account.binding is None:
            raise ParseFailed("this account has no statement adapter and accepts no upload")
        adapter = ADAPTERS.get(account.binding)
        if adapter is None:
            raise ParseFailed(f"no adapter is available yet for {account.binding}")

        # The password opens the file in memory and goes no further: not stored, not logged.
        document = read_document(filename, unlock(content, password))
        try:
            redacted = redactor.redact(document)
        except RedactionError as exc:
            raise RedactionFailed(
                "personal details could not be redacted; nothing was imported"
            ) from exc
        parsed = adapter.parse(redacted.document)
        hashed = hash_rows(parsed.rows, account_id)
        warnings = list(parsed.warnings)
        originals = _original_narrations(adapter, document, parsed, hashed, vault, warnings)
        fingerprint = redacted.report.fingerprint
        if (
            fingerprint
            and account.statement_fingerprint
            and fingerprint != account.statement_fingerprint
        ):
            warnings.append(
                f"this statement's card or account number differs from earlier ones for "
                f"{account.display_name}; check it belongs to this account"
            )
        if (w := _holdings_warning(account, parsed)) is not None:
            warnings.append(w)

        with db.transaction(scope) as s:
            stored = JournalRepository(s).existing_hashes(
                account_id, (h.dedup_hash for h in hashed)
            )
            fresh = [h for h in hashed if h.dedup_hash not in stored]
            known = MappingRepository(s).get_many(h.row.raw_description for h in fresh)
            rules = active_rules(s)
            examples = owner_examples(s)
            masker = build_masker(s)

        # Owner rules come before the model and win over a mapping only the model made.
        known = {
            **known,
            **rule_mappings(
                rules,
                {
                    h.row.raw_description: ("debit" if h.row.amount < 0 else "credit")
                    for h in fresh
                    if not h.row.own_move
                },
                known,
                {
                    h.row.raw_description: originals[h.dedup_hash]
                    for h in fresh
                    if h.dedup_hash in originals
                },
            ),
        }

        unmapped: dict[str, Literal["debit", "credit"]] = {
            h.row.raw_description: ("debit" if h.row.amount < 0 else "credit")
            for h in fresh
            if not h.row.own_move and h.row.raw_description not in known
        }
        mappings: dict[str, MerchantMapping] = dict(known)
        new_model: list[MerchantMapping] = []
        if unmapped:
            categorizer = as_categorizer(client, masker)
            if categorizer is None:
                warnings.append("categorization skipped: no model is configured")
            else:
                result = categorizer.categorize(
                    [Item(d, way) for d, way in unmapped.items()], labels, examples
                )
                warnings.extend(result.warnings)
                mappings.update(result.mappings)
                new_model = list(result.mappings.values())

        with db.transaction(scope) as s:
            return _commit(
                s,
                account,
                filename,
                content,
                parsed,
                hashed,
                mappings,
                new_model,
                warnings,
                redacted.report,
                {h: vault.seal(t) for h, t in originals.items()} if vault else {},
            )


def _original_narrations(
    adapter: Adapter,
    document: Document,
    parsed: ParsedStatement,
    hashed: list[HashedRow],
    vault: Vault | None,
    warnings: list[str],
) -> dict[str, str]:
    """The original narration of each row by dedup hash, or nothing. The adapter reads the
    unredacted document too; its rows must line up with the redacted ones in count, date and
    amount, or none are kept (fail closed: a misaligned original would label the wrong row).
    Never raises, and never puts a narration in a message."""
    if vault is None or parsed.holdings_kind is not None:
        return {}
    try:
        original = adapter.parse(document)
    except Exception as exc:  # the redacted copy parsed; this one is only a convenience
        log.warning("original narrations not kept: %s", type(exc).__name__)
        warnings.append("original narrations could not be kept for this statement")
        return {}
    same = len(original.rows) == len(parsed.rows) == len(hashed) and all(
        o.date == r.date and o.amount == r.amount
        for o, r in zip(original.rows, parsed.rows, strict=True)
    )
    if not same:
        warnings.append("original narrations could not be kept for this statement")
        return {}
    return {h.dedup_hash: o.raw_description for h, o in zip(hashed, original.rows, strict=True)}


def _row(h: HashedRow) -> RowIn:
    return RowIn(
        date=h.row.date,
        amount=h.row.amount,
        narration=h.row.raw_description,
        payee=h.row.merchant or h.row.raw_description,
        dedup_hash=h.dedup_hash,
        own_move=h.row.own_move,
    )


def _commit(
    s: Session,
    account: Account,
    filename: str,
    content: bytes,
    parsed: ParsedStatement,
    hashed: list[HashedRow],
    mappings: dict[str, MerchantMapping],
    new_model: list[MerchantMapping],
    warnings: list[str],
    report: RedactionReport,
    sealed: dict[str, bytes],
) -> UploadResult:
    if new_model:
        MappingRepository(s).save_model(new_model)
    # A file without a period end (Axis) is covered through its latest transaction.
    period_end = parsed.period_end or max((h.row.date for h in hashed), default=None)
    sha = hashlib.sha256(content).hexdigest()
    if ImportHashRepository(s).same_file(account.id, sha):
        warnings.append(
            "this exact file was already uploaded for this account; nothing new was added"
        )
    record = ImportRepository(s).add(
        account.id,
        filename,
        sha,
        period_start=parsed.period_start,
        period_end=period_end,
        rows_inserted=0,
        hashes_ignored=0,
        closing_balance=parsed.closing_balance,
        balance_as_of=parsed.balance_as_of,
        amount_due=parsed.amount_due,
        due_date=parsed.due_date,
        redaction_summary=dict(report.counts),
    )
    if report.fingerprint:
        AccountRepository(s).set_fingerprint(account.id, report.fingerprint)
    posted = post_rows(s, account, record.id, [_row(h) for h in hashed], mappings)
    originals_repo = OriginalRepository(s)
    originals_repo.put_many(account.id, sealed)
    originals_repo.purge_orphans()
    ImportHashRepository(s).add(record.id, account.id, [h.dedup_hash for h in hashed])
    ImportRepository(s).set_counts(record.id, posted.inserted, posted.ignored)
    pairs = pair_in_transit(s)

    if parsed.closing_balance is not None and parsed.balance_as_of is not None:
        if account.group is Group.INVESTMENTS:
            revalue(s, account.id, parsed.balance_as_of, parsed.closing_balance, record.id)
        else:
            # Statements print what is owed on a card as a positive number; the ledger holds a
            # liability as a negative balance. Bank balances are stored as printed.
            amount = (
                -parsed.closing_balance
                if account.type is AccountType.CREDIT_CARD or account.type is AccountType.LOAN
                else parsed.closing_balance
            )
            record_assertion(s, account.id, parsed.balance_as_of, amount, record.id)
    recompute_opening(s, account.id)

    open_gaps = account_gaps(s, account.id)
    return UploadResult(
        import_id=record.id,
        rows_inserted=posted.inserted,
        hashes_ignored=posted.ignored,
        pairs_merged=pairs,
        uncategorized=posted.uncategorized,
        gaps=open_gaps,
        warnings=tuple(warnings),
        redaction=dict(report.counts),
    )

"""HTTP routes. Each is validation, one service or report call, and response mapping."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import UUID

from cfo.api.app import Deps
from cfo.api.catalog import build_catalog, resolve_binding
from cfo.api.chat import ChatRegistry, add_chat_routes
from cfo.api.deps import ScopeDep
from cfo.api.labels import apply_labels
from cfo.api.originals import attach_originals
from cfo.api.rules_routes import add_rule_routes
from cfo.api.sample import default_seed_client, load_sample
from cfo.core.errors import ConflictError, NotFoundError
from cfo.core.types import AccountRole, AccountType, Direction, Scope
from cfo.ingest.masking import build_masker
from cfo.ingest.retry import retry_categorization
from cfo.ingest.upload import upload_statement
from cfo.ledger import reports
from cfo.ledger.journal import ignore, recategorize, remove_import, revalue
from cfo.ledger.repositories.accounts import (
    AccountRepository,
    PseudonymLabelRepository,
    RedactionTermRepository,
    SettingsRepository,
)
from cfo.ledger.repositories.people import PeopleRepository
from cfo.ledger.rules_service import seed_starter_rules
from cfo.ledger.setup import (
    AccountInput,
    CategoryInput,
    add_account,
    add_category,
    complete_setup,
    create_ledger_defaults,
    delete_account,
    delete_category,
    edit_account,
    edit_category,
    is_set_up,
    merge_category,
    retire_category,
)
from cfo.parse.base import MAX_BYTES
from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field, field_validator

Json = dict[str, Any]
MonthQ = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]
_UNSET: Any = object()


class AccountIn(BaseModel):
    type: AccountType
    institution: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=60)
    cycle_day: int | None = Field(default=None, ge=1, le=31)
    opening_value_paise: int | None = None
    opening_date: date | None = None


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    institution: str | None = Field(default=None, min_length=1, max_length=60)
    cycle_day: int | None = Field(default=None, ge=1, le=31)


class ValueIn(BaseModel):
    as_of: date
    amount_paise: int


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    direction: Direction
    description: str = Field(max_length=200)
    parent_id: UUID | None = None


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    keywords: str | None = Field(default=None, max_length=1000)


class MergeIn(BaseModel):
    into_id: UUID


class RecategorizeIn(BaseModel):
    account_id: UUID


class SettingsPatch(BaseModel):
    """Only the fields sent change. A null allowance removes it."""

    min_cash_buffer_paise: int | None = Field(default=None, ge=0)
    monthly_allowance_paise: int | None = Field(default=_UNSET, ge=0)


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    family_names: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("name")
    @classmethod
    def _named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a person needs a name")
        return value


class TermsIn(BaseModel):
    terms: list[str] = Field(max_length=200)


class LabelIn(BaseModel):
    token: str = Field(pattern=r"^\[[A-Z_]+:[0-9a-f]{4}\]$")
    label: str = Field(max_length=80)


def _settings_json(s: Any) -> Json:
    st = SettingsRepository(s).get()
    return {
        "min_cash_buffer": reports.money(st.min_cash_buffer),
        "monthly_allowance": None
        if st.monthly_allowance is None
        else reports.money(st.monthly_allowance),
        "setup_completed_at": st.setup_completed_at.isoformat() if st.setup_completed_at else None,
    }


def build_router(deps: Deps, chats: ChatRegistry) -> APIRouter:
    top = APIRouter()
    r = APIRouter(prefix="/people/{person_id}")
    db = deps.db

    def today() -> date:
        return deps.clock()

    def data(s: Any) -> reports.Data:
        return reports.load(s, today())

    def labelled(scope: Any, value: Any) -> Any:
        """Pseudonym tokens shown as the owner's labels: the cockpit only, never the agent."""
        with db.transaction(scope) as s:
            return apply_labels(value, PseudonymLabelRepository(s).all())

    @top.get("/health")
    def health() -> Json:
        return {"status": "ok"}

    @top.get("/catalog")
    def catalog() -> Json:
        return build_catalog()

    # people ---------------------------------------------------------------------------

    @top.post("/people", status_code=201)
    def create_person(body: PersonIn) -> Json:
        """Create a person by name. Their ledger is created with them, with the default
        categories, and their name and any family names seed its redaction terms."""
        with db.transaction() as s:
            person, ledger = PeopleRepository(s).create(body.name, body.family_names)
            seed_starter_rules(s, Scope.of(ledger.id))
        return {"id": str(person.id), "name": person.name, "ledger_id": str(ledger.id)}

    @top.get("/people")
    def list_people() -> list[Json]:
        with db.transaction() as s:
            return [
                {"id": str(p.id), "name": p.name, "ledger_id": str(led.id)}
                for p, led in PeopleRepository(s).list_all()
            ]

    @top.post("/sample", status_code=201)
    def sample() -> Json:
        result = load_sample(db, today(), default_seed_client())
        return {
            "person_id": str(result.person_id),
            "accounts": result.accounts,
            "uploads": len(result.uploads),
        }

    # setup ----------------------------------------------------------------------------

    @r.get("/setup")
    def setup_state(scope: ScopeDep) -> Json:
        with db.transaction(scope) as s:
            create_ledger_defaults(s)  # a ledger from before the upgrade gets its categories now
            st = SettingsRepository(s).get()
            accounts = len(AccountRepository(s).list_all(AccountRole.REAL))
            return {
                "completed": st.setup_completed_at is not None and is_set_up(s),
                "accounts": accounts,
            }

    @r.post("/setup/complete")
    def setup_complete(scope: ScopeDep) -> Json:
        with db.transaction(scope) as s:
            complete_setup(s, datetime.now(UTC))
        return {"completed": True}

    # accounts -------------------------------------------------------------------------

    @r.post("/accounts", status_code=201)
    def create_account(scope: ScopeDep, body: AccountIn) -> Json:
        inp = AccountInput(
            body.type,
            body.institution,
            body.name,
            body.cycle_day,
            body.opening_value_paise,
            body.opening_date,
        )
        with db.transaction(scope) as s:
            account = add_account(s, inp, today(), resolve_binding(body.institution, body.type))
            return reports.plain(reports.account_json(account))  # type: ignore[no-any-return]

    @r.get("/accounts")
    def list_accounts(scope: ScopeDep) -> list[Json]:
        with db.transaction(scope) as s:
            sheet = reports.balance_sheet_report(data(s))
        return [a for g in sheet["groups"] for a in g["accounts"] if a["role"] == "real"]

    @r.get("/accounts/tree")
    def accounts_tree(scope: ScopeDep) -> Json:
        with db.transaction(scope) as s:
            return reports.accounts_tree_report(data(s))

    @r.get("/accounts/{account_id}")
    def account_page(scope: ScopeDep, account_id: UUID) -> Json:
        with db.transaction(scope) as s:
            account = AccountRepository(s).get(account_id)
            if account is None or account.role is not AccountRole.REAL:
                raise NotFoundError(f"unknown account {account_id}")
            page = reports.account_report(data(s), account_id)
        return labelled(scope, page)  # type: ignore[no-any-return]

    @r.patch("/accounts/{account_id}")
    def patch_account(scope: ScopeDep, account_id: UUID, body: AccountPatch) -> Json:
        with db.transaction(scope) as s:
            account = edit_account(
                s,
                account_id,
                name=body.name,
                institution=body.institution,
                cycle_day=body.cycle_day,
            )
            return reports.plain(reports.account_json(account))  # type: ignore[no-any-return]

    @r.get("/accounts/{account_id}/usage")
    def account_usage(scope: ScopeDep, account_id: UUID) -> Json:
        with db.transaction(scope) as s:
            if AccountRepository(s).get(account_id) is None:
                raise NotFoundError(f"unknown account {account_id}")
            u = AccountRepository(s).usage(account_id)
            return {"postings": u.postings, "imports": u.imports}

    @r.delete("/accounts/{account_id}", status_code=204)
    def remove_account(scope: ScopeDep, account_id: UUID) -> Response:
        with db.transaction(scope) as s:
            delete_account(s, account_id)
        return Response(status_code=204)

    @r.post("/accounts/{account_id}/value")
    def set_value(scope: ScopeDep, account_id: UUID, body: ValueIn) -> Json:
        with db.transaction(scope) as s:
            change = revalue(s, account_id, body.as_of, body.amount_paise)
        return {"change": reports.money(change)}

    # statements -----------------------------------------------------------------------

    @r.post("/accounts/{account_id}/uploads")
    def upload(
        scope: ScopeDep,
        account_id: UUID,
        file: Annotated[UploadFile, File()],
        password: Annotated[str | None, Form()] = None,
    ) -> Json:
        content = file.file.read(MAX_BYTES + 1)
        result = upload_statement(
            db,
            account_id,
            file.filename or "upload",
            content,
            deps.client,
            today(),
            password or None,
            scope,
            deps.vault,
        )
        return {
            "import_id": str(result.import_id),
            "rows_inserted": result.rows_inserted,
            "hashes_ignored": result.hashes_ignored,
            "pairs_merged": result.pairs_merged,
            "uncategorized": result.uncategorized,
            "gaps": result.gaps,
            "warnings": list(result.warnings),
            "redaction": result.redaction,
        }

    @r.delete("/imports/{import_id}")
    def delete_import(scope: ScopeDep, import_id: UUID) -> Json:
        """Remove an uploaded statement and everything that came from it."""
        with db.transaction(scope) as s:
            result = remove_import(s, import_id)
        return {
            "transactions_deleted": result.transactions_deleted,
            "rebalanced": result.rebalanced,
        }

    @r.post("/categorization/retry")
    def retry(scope: ScopeDep) -> Json:
        if deps.client is None:
            raise ConflictError("no model is configured")
        result = retry_categorization(db, deps.client, scope, deps.vault)
        return {"rows_updated": result.rows_updated, "warnings": list(result.warnings)}

    # categories -----------------------------------------------------------------------

    @r.get("/categories")
    def categories(scope: ScopeDep) -> Json:
        with db.transaction(scope) as s:
            return reports.categories_report(data(s))

    @r.post("/categories", status_code=201)
    def create_category(scope: ScopeDep, body: CategoryIn) -> Json:
        with db.transaction(scope) as s:
            account = add_category(
                s, CategoryInput(body.name, body.direction, body.description, body.parent_id)
            )
            return reports.plain(reports.account_json(account))  # type: ignore[no-any-return]

    @r.patch("/categories/{category_id}")
    def patch_category(scope: ScopeDep, category_id: UUID, body: CategoryPatch) -> Json:
        with db.transaction(scope) as s:
            account = edit_category(
                s, category_id, name=body.name, description=body.description, keywords=body.keywords
            )
            return reports.plain(reports.account_json(account))  # type: ignore[no-any-return]

    @r.post("/categories/{category_id}/merge")
    def merge(scope: ScopeDep, category_id: UUID, body: MergeIn) -> Json:
        with db.transaction(scope) as s:
            return {"moved": merge_category(s, category_id, body.into_id, today())}

    @r.post("/categories/{category_id}/retire")
    def retire(scope: ScopeDep, category_id: UUID) -> Json:
        with db.transaction(scope) as s:
            retire_category(s, category_id, today())
        return {"retired": True}

    @r.delete("/categories/{category_id}", status_code=204)
    def remove_category(scope: ScopeDep, category_id: UUID) -> Response:
        with db.transaction(scope) as s:
            delete_category(s, category_id)
        return Response(status_code=204)

    # transactions ---------------------------------------------------------------------

    @r.get("/transactions")
    def transactions(
        scope: ScopeDep,
        account_id: UUID | None = None,
        category_id: UUID | None = None,
        month: MonthQ = None,
        q: Annotated[str | None, Query(max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=2000)] = 500,
    ) -> list[Json]:
        with db.transaction(scope) as s:
            rows = reports.transactions_report(
                data(s),
                account_id=account_id,
                category_id=category_id,
                month=month,
                q=q,
                limit=limit,
            )
            attach_originals(s, deps.vault, rows, "id")
        return labelled(scope, rows)  # type: ignore[no-any-return]

    @r.patch("/transactions/{tx_id}/category")
    def change_category(scope: ScopeDep, tx_id: UUID, body: RecategorizeIn) -> Json:
        with db.transaction(scope) as s:
            return {"changed": recategorize(s, tx_id, body.account_id)}

    @r.post("/transactions/{tx_id}/ignore")
    def ignore_row(scope: ScopeDep, tx_id: UUID) -> Json:
        with db.transaction(scope) as s:
            ignore(s, tx_id)
        return {"ignored": True}

    # reports --------------------------------------------------------------------------

    @r.get("/reports/overview")
    def overview(scope: ScopeDep) -> Json:
        with db.transaction(scope) as s:
            out = reports.overview_report(data(s))
        return labelled(scope, out)  # type: ignore[no-any-return]

    @r.get("/reports/balance-sheet")
    def balance_sheet(scope: ScopeDep, as_of: date | None = None) -> Json:
        with db.transaction(scope) as s:
            return reports.balance_sheet_report(data(s), as_of)

    @r.get("/reports/income-statement")
    def income_statement(scope: ScopeDep, month: MonthQ = None) -> Json:
        with db.transaction(scope) as s:
            return reports.income_statement_report(data(s), month)

    @r.get("/reports/safe-to-spend")
    def safe_to_spend(scope: ScopeDep) -> Json:
        with db.transaction(scope) as s:
            return reports.safe_to_spend_report(data(s))

    @r.get("/reports/leaks")
    def leaks(scope: ScopeDep, month: MonthQ = None) -> Json:
        with db.transaction(scope) as s:
            out = reports.leaks_report(data(s), month)
        return labelled(scope, out)  # type: ignore[no-any-return]

    @r.get("/inbox")
    def inbox(scope: ScopeDep) -> list[Json]:
        with db.transaction(scope) as s:
            out = reports.inbox_report(data(s))
            attach_originals(s, deps.vault, out, "transaction_id")
        return labelled(scope, out)  # type: ignore[no-any-return]

    # settings -------------------------------------------------------------------------

    @r.get("/settings")
    def get_settings(scope: ScopeDep) -> Json:
        with db.transaction(scope) as s:
            return _settings_json(s)

    @r.patch("/settings")
    def patch_settings(scope: ScopeDep, body: SettingsPatch) -> Json:
        fields: dict[str, Any] = {}
        if body.min_cash_buffer_paise is not None:
            fields["min_cash_buffer"] = body.min_cash_buffer_paise
        if body.monthly_allowance_paise is not _UNSET:
            fields["monthly_allowance"] = body.monthly_allowance_paise
        with db.transaction(scope) as s:
            SettingsRepository(s).update(**fields)
            return _settings_json(s)

    # privacy --------------------------------------------------------------------------

    @r.get("/privacy/terms")
    def get_terms(scope: ScopeDep) -> Json:
        with db.transaction(scope) as s:
            return {"terms": RedactionTermRepository(s).list_all()}

    @r.put("/privacy/terms")
    def put_terms(scope: ScopeDep, body: TermsIn) -> Json:
        with db.transaction(scope) as s:
            return {"terms": RedactionTermRepository(s).replace(body.terms)}

    @r.get("/privacy/preview")
    def privacy_preview(scope: ScopeDep, limit: int = Query(default=12, ge=1, le=50)) -> Json:
        """Exactly what would be sent to the model for the latest narrations. Local only."""
        with db.transaction(scope) as s:
            masker = build_masker(s)
            seen: dict[str, None] = {}
            for t in reversed(data(s).transactions):
                if t.source != "import":
                    continue
                seen.setdefault(t.narration, None)
                if len(seen) >= limit:
                    break
            return {
                "examples": [{"original": d, "sent": masker.narration(d)} for d in seen],
                "aliases": [{"real": k, "alias": v} for k, v in masker.aliases.items()],
            }

    @r.get("/privacy/labels")
    def get_labels(scope: ScopeDep) -> list[Json]:
        with db.transaction(scope) as s:
            return reports.privacy_tokens(data(s), PseudonymLabelRepository(s).all())

    @r.put("/privacy/labels")
    def put_label(scope: ScopeDep, body: LabelIn) -> Json:
        with db.transaction(scope) as s:
            PseudonymLabelRepository(s).set(body.token, body.label)
        return {"token": body.token, "label": body.label.strip() or None}

    add_chat_routes(r, chats)
    add_rule_routes(r, deps)
    top.include_router(r)
    return top


__all__ = ["build_router"]

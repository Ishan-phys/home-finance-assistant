"""Owner rules over HTTP: list, create, edit, reorder, preview and apply."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cfo.api.app import Deps
from cfo.api.deps import ScopeDep
from cfo.core.chart import IN_TRANSIT
from cfo.core.errors import InvalidInput, NotFoundError
from cfo.core.types import AccountRole
from cfo.ledger.repositories.accounts import AccountRepository
from cfo.ledger.repositories.rules import RuleRepository
from cfo.ledger.rules_service import apply_rule, preview_rule
from cfo.rules import MatchMode, Rule, Way
from fastapi import APIRouter, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

Json = dict[str, Any]


class RuleIn(BaseModel):
    label: str = Field(default="", max_length=80)
    match_text: str = Field(min_length=1, max_length=200)
    mode: MatchMode = MatchMode.CONTAINS
    way: Way = "any"
    target_id: UUID
    apply_now: bool = False

    @field_validator("match_text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a rule needs some text to match")
        return value


class RulePatch(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    match_text: str | None = Field(default=None, min_length=1, max_length=200)
    mode: MatchMode | None = None
    way: Way | None = None
    target_id: UUID | None = None

    @field_validator("match_text")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("a rule needs some text to match")
        return value


class ReorderIn(BaseModel):
    ids: list[UUID] = Field(max_length=500)


def _target_path(s: Session, target_id: UUID) -> str:
    target = AccountRepository(s).get(target_id)
    ok = (
        target is not None
        and target.active
        and (target.role is AccountRole.CATEGORY or target.path == IN_TRANSIT)
    )
    if not ok or target is None:
        raise InvalidInput("pick a category, or 'Own account or investment'")
    return target.path


def _json(s: Session, rule: Rule) -> Json:
    account = AccountRepository(s).by_path(rule.target)
    return {
        "id": rule.id,
        "label": rule.label,
        "match_text": rule.match_text,
        "mode": rule.mode.value,
        "way": rule.way,
        "position": rule.position,
        "builtin": rule.builtin,
        "target": {
            "id": account.id if account else None,
            "name": account.display_name if account else rule.target,
            "path": rule.target,
        },
    }


def add_rule_routes(r: APIRouter, deps: Deps) -> None:
    db = deps.db

    @r.get("/rules")
    def list_rules(scope: ScopeDep) -> list[Json]:
        with db.transaction(scope) as s:
            return [_json(s, x) for x in RuleRepository(s).list_all()]

    @r.post("/rules", status_code=201)
    def create_rule(scope: ScopeDep, body: RuleIn) -> Json:
        with db.transaction(scope) as s:
            rule = RuleRepository(s).add(
                body.label, body.match_text, body.mode, body.way, _target_path(s, body.target_id)
            )
            applied = apply_rule(s, rule) if body.apply_now else 0
            return {**_json(s, rule), "applied": applied}

    @r.patch("/rules/{rule_id}")
    def edit_rule(scope: ScopeDep, rule_id: UUID, body: RulePatch) -> Json:
        with db.transaction(scope) as s:
            target = _target_path(s, body.target_id) if body.target_id else None
            rule = RuleRepository(s).update(
                rule_id,
                label=body.label,
                match_text=body.match_text,
                mode=body.mode,
                way=body.way,
                target=target,
            )
            return _json(s, rule)

    @r.delete("/rules/{rule_id}", status_code=204)
    def remove_rule(scope: ScopeDep, rule_id: UUID) -> Response:
        with db.transaction(scope) as s:
            RuleRepository(s).delete(rule_id)
        return Response(status_code=204)

    @r.post("/rules/reorder")
    def reorder_rules(scope: ScopeDep, body: ReorderIn) -> list[Json]:
        with db.transaction(scope) as s:
            repo = RuleRepository(s)
            repo.reorder(body.ids)
            return [_json(s, x) for x in repo.list_all()]

    @r.post("/rules/preview")
    def preview(scope: ScopeDep, body: RuleIn) -> Json:
        """How many existing transactions the rule would move, without saving anything."""
        with db.transaction(scope) as s:
            draft = Rule(
                UUID(int=0), body.label or body.match_text, body.match_text, body.mode, body.way,
                _target_path(s, body.target_id), 0,
            )  # fmt: skip
            return {"matches": preview_rule(s, draft)}

    @r.post("/rules/{rule_id}/apply")
    def apply(scope: ScopeDep, rule_id: UUID) -> Json:
        with db.transaction(scope) as s:
            rule = RuleRepository(s).get(rule_id)
            if rule is None:
                raise NotFoundError(f"unknown rule {rule_id}")
            return {"changed": apply_rule(s, rule)}

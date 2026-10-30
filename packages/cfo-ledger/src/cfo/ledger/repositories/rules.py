"""Owner rules, stored per ledger. The matching itself lives in cfo-rules."""

from __future__ import annotations

from collections.abc import Sequence

from cfo.core.errors import InvalidInput, NotFoundError
from cfo.core.ids import Id, new_id
from cfo.ledger.repositories.models import RuleRow
from cfo.ledger.repositories.scope import ScopedRepository
from cfo.rules import MatchMode, Rule, Way
from sqlalchemy import func, select, update


def _rule(r: RuleRow) -> Rule:
    return Rule(
        r.id, r.label, r.match_text, MatchMode(r.mode), r.way, r.target, r.position, r.builtin
    )  # type: ignore[arg-type]


class RuleRepository(ScopedRepository):
    def list_all(self) -> list[Rule]:
        q = select(RuleRow).where(self.in_scope(RuleRow.ledger_id))
        return [_rule(r) for r in self.s.scalars(q.order_by(RuleRow.position, RuleRow.id))]

    def get(self, rule_id: Id) -> Rule | None:
        row = self._row(rule_id)
        return _rule(row) if row else None

    def _row(self, rule_id: Id) -> RuleRow | None:
        return self.s.scalars(
            select(RuleRow).where(RuleRow.id == rule_id, self.in_scope(RuleRow.ledger_id))
        ).first()

    def add(
        self,
        label: str,
        match_text: str,
        mode: MatchMode,
        way: Way,
        target: str,
        *,
        builtin: bool = False,
    ) -> Rule:
        last = self.s.scalar(
            select(func.max(RuleRow.position)).where(RuleRow.ledger_id == self.ledger_id)
        )
        rule = Rule(
            new_id(),
            label.strip() or match_text.strip(),
            match_text,
            mode,
            way,
            target,
            0 if last is None else last + 1,
            builtin,
        )
        self.s.add(
            RuleRow(
                id=rule.id,
                ledger_id=self.ledger_id,
                label=rule.label,
                match_text=rule.match_text,
                mode=rule.mode.value,
                way=rule.way,
                target=rule.target,
                position=rule.position,
                builtin=builtin,
            )  # fmt: skip
        )
        self.s.flush()
        return rule

    def update(
        self,
        rule_id: Id,
        *,
        label: str | None = None,
        match_text: str | None = None,
        mode: MatchMode | None = None,
        way: Way | None = None,
        target: str | None = None,
    ) -> Rule:
        row = self._row(rule_id)
        if row is None:
            raise NotFoundError(f"unknown rule {rule_id}")
        fresh = Rule(
            row.id,
            row.label if label is None else label.strip() or row.label,
            row.match_text if match_text is None else match_text,
            MatchMode(row.mode) if mode is None else mode,
            row.way if way is None else way,  # type: ignore[arg-type]
            row.target if target is None else target,
            row.position,
            row.builtin,
        )
        row.label, row.match_text, row.mode = fresh.label, fresh.match_text, fresh.mode.value
        row.way, row.target = fresh.way, fresh.target
        self.s.flush()
        return fresh

    def delete(self, rule_id: Id) -> None:
        row = self._row(rule_id)
        if row is None:
            raise NotFoundError(f"unknown rule {rule_id}")
        self.s.delete(row)
        self.s.flush()

    def reorder(self, ids: Sequence[Id]) -> None:
        """`ids` must be every rule of the ledger, in the new order."""
        current = {r.id for r in self.list_all()}
        if set(ids) != current or len(ids) != len(current):
            raise InvalidInput("send every rule exactly once to reorder them")
        for position, rule_id in enumerate(ids):
            self.s.execute(
                update(RuleRow)
                .where(RuleRow.id == rule_id, RuleRow.ledger_id == self.ledger_id)
                .values(position=position)
            )
        self.s.flush()

    def repoint(self, from_target: str, to_target: str) -> int:
        """Move every rule from one account path to another (a category merge)."""
        result = self.s.execute(
            update(RuleRow)
            .where(RuleRow.ledger_id == self.ledger_id, RuleRow.target == from_target)
            .values(target=to_target)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def delete_targeting(self, target: str) -> int:
        rows = self.s.scalars(
            select(RuleRow).where(RuleRow.ledger_id == self.ledger_id, RuleRow.target == target)
        ).all()
        for r in rows:
            self.s.delete(r)
        self.s.flush()
        return len(rows)

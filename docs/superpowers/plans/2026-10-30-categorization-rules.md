# Categorization rules, readable narrations and card payments: implementation plan

> **For agentic workers:** execute task by task with superpowers:executing-plans; steps use `- [ ]`.

**Goal:** Owner rules, encrypted original narrations, card payments as transfers, better defaults and
redaction, enforced double entry, and a security audit.

**Architecture:** Pure `cfo-rules` engine and `cfo-vault` cipher, both consumed by `cfo-ledger`
repositories and the `cfo-ingest` pipeline; the API exposes them; the web app shows them.

**Tech Stack:** Python 3.13, SQLAlchemy, Alembic, Postgres 16, FastAPI, Next.js, `cryptography`.

**Spec:** `docs/superpowers/specs/2026-10-30-categorization-rules-design.md`

## Global Constraints

- Tests use the throwaway Postgres from `cfo.testing.pg`. Never set `CFO_TEST_DATABASE_URL` to the running stack's database (fixtures truncate tables).
- The original narration never reaches a model, the chat tools, logs or error text.
- No regex rules. Match modes are `contains` and `starts_with`, case-insensitive on whitespace-normalised text.
- Authority order: owner's manual change, exact owner mapping, rules by position, model, Uncategorized.
- Dedup hashes stay computed on the redacted text.
- Amount band to the model is off by default.
- Migration numbers continue from 0010. Run `uv run ruff check .` and `uv run pytest` before each commit.

## Review Focus

- Rule text that is empty or only whitespace must be rejected (it would match everything).
- A rule must not overwrite a category the owner set by hand.
- Two rules matching one row: the lower `position` wins, deterministically.
- A key file that is missing or wrong must degrade to the redacted text, not crash a list endpoint.
- Re-uploading a statement must not duplicate transactions when originals are attached.
- An unbalanced write must fail at commit with a readable error.

---

### Task 1: `cfo-rules` engine

**Files:** Create `packages/cfo-rules/{pyproject.toml,src/cfo/rules/__init__.py,src/cfo/rules/engine.py,tests/test_engine.py}`.

**Produces:** `MatchMode`, `Rule`, `normalize(text) -> str`, `first_match(rules, narration, way) -> Rule | None`, `suggest_match_text(narration) -> str`.

- [ ] Tests: `test_contains_is_case_and_space_insensitive`, `test_starts_with_only_matches_prefix`, `test_way_filters_direction`, `test_lowest_position_wins`, `test_blank_match_text_rejected` (`Rule(...)` raises `ValueError`), `test_suggest_drops_refs_and_handles` (`"UPI-URBAN COMPANY LIMITE-PAYTM-[VPA:06e6]-YESB0PTMUPI-[ID:1552]-UPI"` suggests `"URBAN COMPANY LIMITE"`), `test_suggest_keeps_person_token` (`"UPI-[PERSON:5e31]-[VPA:19cd]-HDFC[ID:db1e]-[ID:d938]-RENT"` suggests `"[PERSON:5e31]"`).
- [ ] Implement in `engine.py`; suggestion takes the first non-noise segment after the `UPI-`/`IMPS-`/`NEFT-` prefix, like `cfo.categorize.merchants`.
- [ ] Run `uv run pytest packages/cfo-rules -q`; commit.

### Task 2: Enforced double entry

**Files:** Create `packages/cfo-ledger/alembic/versions/0011_balanced_postings.py`, `packages/cfo-ledger/src/cfo/ledger/verify.py`, `packages/cfo-ledger/tests/test_balanced.py`. Modify `repositories/transactions.py` (`add`, `add_posting`).

**Produces:** `verify_books(s: Session) -> list[Id]` (ids of unbalanced transactions); Postgres deferred constraint trigger `trg_postings_balanced`.

- [ ] Tests: `test_unbalanced_commit_fails` (insert a one-sided transaction, commit raises), `test_verify_books_empty_after_upload_pair_recategorize`, `test_add_rejects_unbalanced` (readable `InvalidInput`).
- [ ] Migration creates the constraint trigger (`DEFERRABLE INITIALLY DEFERRED`, row level, on insert/update/delete of `postings`) summing `amount` per `transaction_id`, ignoring transactions with no postings.
- [ ] `JournalRepository.add` raises `InvalidInput("transaction does not balance")` when `sum(p.amount) != 0`.
- [ ] Run the full ledger and ingest test suites; commit.

### Task 3: Rules storage, application and API

**Files:** Migration `0012_rules.py`; model `RuleRow` in `models.py`; `RuleRepository` in new `repositories/rules.py`; `cfo/ledger/rules_service.py`; modify `ingest/upload.py`, `ingest/retry.py`, `ledger/journal.py`; API routes in `api/src/cfo/api/routes.py`; tests in ledger and api.

**Produces:** `RuleRepository.list_all() -> list[Rule]`, `add(...)`, `update(...)`, `delete(id)`, `reorder(ids)`; `preview_rule(s, rule) -> int`; `apply_rule(s, rule) -> int` (only rows still Uncategorized or model-categorized, never `Origin.OWNER`); routes `GET/POST /rules`, `PATCH/DELETE /rules/{id}`, `POST /rules/reorder`, `POST /rules/preview`, `POST /rules/{id}/apply`.

- [ ] Tests: `test_rule_applies_on_upload_before_model`, `test_apply_rule_skips_owner_set`, `test_transfer_rule_pairs_card_payment` (bank debit `... CRED ...` plus card credit pair and drop out of spending), `test_rule_routes_crud_and_reorder`, `test_preview_counts_matches`.
- [ ] Wire rules into `upload_statement` between saved mappings and the model; into `retry_categorization`; `recategorize` accepts `always: RuleSpec | None` to create the rule in the same transaction.
- [ ] Run suites; commit.

### Task 4: Categories, Refunds, starter rules

**Files:** Modify `cfo-core/src/cfo/core/chart.py`, `cfo-categorize/src/cfo/categorize/categorizer.py` (prompt), `ledger/setup.py`; tests alongside.

- [ ] Add `Expenses:Grooming`, `Expenses:Fitness`, `Expenses:HouseholdHelp`, `Income:Refunds` to `DEFAULT_CATEGORIES`; upgrade path creates them for existing ledgers.
- [ ] Prompt: a refund credit goes to Refunds. Update the `test_categorizer` expectation.
- [ ] Seed starter rules (card bill patterns, cashback) as editable rows at ledger setup.
- [ ] Category keywords: column `keywords` on accounts, appended to the description the model sees and applied as lowest-priority contains rules.

### Task 5: Redaction keeps classifying words

**Files:** Modify `packages/cfo-redact/src/cfo/redact/redactor.py`, `names.py`; tests `packages/cfo-redact/tests`.

- [ ] Tests from the spec table: `SHARMA ELECTRICALS` keeps `ELECTRICALS`; `SAGAR RATNA` on a `POS` line and on a card statement stays unredacted; `VIKRAM KAPOOR` payee stays a `[PERSON:..]` token.
- [ ] Extend business words; skip name lists for card-statement merchants and `POS`/`ECOM` lines.

### Task 6: Owner examples reach the model

**Files:** Modify `cfo-categorize/src/cfo/categorize/{port.py,categorizer.py,decisions.py}`; `ingest/upload.py`, `ingest/retry.py`.

**Produces:** `Example(description: str, direction: Way, label: str)`; `Categorizer.categorize(items, labels, examples=())`.

- [ ] Tests: examples sharing a token with the item are chosen first, capped at 20; examples are masked; amount band absent unless the setting is on.
- [ ] Repository method returning the owner's mapped narrations as `Example`s.

### Task 7: Encrypted originals

**Files:** Create `packages/cfo-vault/...`; migration `0013_transaction_originals.py`; repo `OriginalRepository`; modify `ingest/upload.py`, `api/routes.py` and report builders.

**Produces:** `Vault.seal(text) -> bytes`, `Vault.open(blob) -> str`, `FernetVault(key)`, `load_vault(env, key_file) -> Vault | None`; transaction and inbox responses carry `original` when present.

- [ ] Tests: round trip; wrong key returns `None`/falls back; originals never appear in `/privacy` preview or chat tool output; re-upload attaches originals without new transactions; row-count mismatch stores none.
- [ ] Parse the original and the redacted document, pair rows by position, seal and store.

### Task 8: Visible failures and web UI

**Files:** `api` upload and inbox responses; `web/src/components/{inbox/inbox-list.tsx,transactions/category-picker.tsx,transactions/txn-table.tsx}`; new `web/src/app/rules/page.tsx` and `web/src/components/rules/rules-page.tsx`; sidebar link.

- [ ] Persist the categorization outcome per import; inbox shows "N rows not categorized" with Retry on `/categorization/retry`.
- [ ] Show `original` under the payee in inbox and picker; "Always do this for [text]" with a live match count; Rules page with list, reorder, edit, delete.
- [ ] `npm run lint` and `npm run build` in `web`.

### Task 9: Security audit

- [ ] Write `docs/security/2026-10-30-audit.md`: findings with severity, file and line, fix. Cover auth and scope isolation, SQL, upload handling (size, type, password handling), secrets in `.env`, logging, CORS, dependencies (`pip-audit`, `npm audit`), the new vault and rules routes. Fix what is small; list the rest.

## Self-review

Coverage: spec sections 1 to 6 map to tasks 7, 3, 4, 8, 2, 5 and 6; the audit is task 9. Deviation to flag in the PR: a `transfer` rule sends the counter side to money in transit and relies on pairing to find the other account, rather than naming a destination account.

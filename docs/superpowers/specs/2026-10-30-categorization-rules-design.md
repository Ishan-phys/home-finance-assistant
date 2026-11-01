# Categorization rules, readable narrations and card payments: design

Date: 2026-10-30. Status: draft for the owner's approval.

## Why

First real use of the app (HDFC bank, HDFC card, Axis card) showed that categorizing is slow
and wrong in ways the owner cannot fix:

- Statement text is redacted before it is stored, so a narration reads `[PERSON:ab12]`. A human
  cannot tell what a row is, and a rule such as "payments to Vikram Kapoor are rent" cannot be
  written because the name is never kept.
- The only memory is an exact-narration mapping. UPI narrations carry reference numbers, so one
  correction rarely applies to the next payment.
- Urban Company (booking household help) lands in Shopping, rent is missed, haircuts, spa, gym and
  coaching have no category, and money-in has no Refund class.
- A credit card bill paid from the bank (directly or through CRED) shows as spending.
- On the Axis card upload everything stayed Uncategorized. The parser reads that PDF correctly
  (14 of 14 rows) and the same categorizer labels 13 of 14 of its lines when run alone, so the
  real upload failed some other way (cause not reproduced) and nothing prompted a retry.

## Goals

1. Show the original narration wherever the owner categorizes.
2. Owner rules: "if the narration contains X, then Y", created from a correction and from a Rules page.
3. Card payments (and any own-account move) are transfers, whatever channel was used.
4. More default categories, a Refunds category for money in, and keywords on a category.
5. A failed or skipped categorization is visible and retryable from the inbox.
6. Each concern is its own module with a narrow interface.
7. Double entry is enforced by the system, not by each caller (section 5).
8. Redaction keeps what is needed to classify, and the owner's labels reach the model with the
   redacted text (section 6).
9. A security audit of the repo, including the new stored data, as the last step.

## Non-goals

- Regex or multi-condition rules, amount conditions, learning from corrections (first version
  is contains / starts-with, one condition, first match wins).
- Any change to which text leaves the machine. Models, the chat assistant and logs still see only
  masked text.
- A new Axis bank-account parser (the Axis problem was the card).

## Anti-goals (failure even if it works)

- The original narration reaching a model, the chat tools, logs or an error message.
- A rule silently overriding something the owner set by hand.
- A card payment counted as spending and again as the card's own purchases.
- Re-uploading a statement creating duplicate transactions.

## Decisions made with the owner

- Store the original narration locally, encrypted at rest. Reason: redacted text is not
  understandable for a human categorizing.
- Create rules both from a "always do this for ..." option when correcting a transaction and from a
  Rules page.
- A card payment is a transfer to the card account, the same for CRED, a direct repayment or UPI.

## Design

### Modules (each independently testable)

| Module | Job | Depends on |
|---|---|---|
| `cfo-vault` (new) | `Vault` protocol: `seal(text) -> bytes`, `open(bytes) -> str`. Fernet implementation; a fake for tests. Nothing else knows the cipher. | stdlib, `cryptography` |
| `cfo-rules` (new) | Pure engine. `Rule(id, label, match_text, mode, way, action, position)`, `first_match(rules, narration, way) -> Rule | None`, `suggest_match_text(narration)`. No database, no web, no model. | `cfo-core` |
| `cfo-ledger` | Tables and repositories for rules and sealed originals; applying rules to existing rows; seeding new default categories. | vault, rules |
| `cfo-ingest` | Pipeline order becomes: read, parse original and redacted, seal originals, rules, saved owner mappings, model for the rest, journal. | rules, vault |
| `api` | Routes: rules CRUD and reorder, rule preview, apply-to-existing, transaction narration, category keywords. | all of the above |
| `web` | Narration line in inbox and picker; "always do this" option; Rules page. | api |

### 1. Original narration

- A new table `transaction_originals(transaction_id, ciphertext)`, separate from the journal so
  it can be dropped or rotated on its own. Ledger-scoped like every other table.
- Key: from `NARRATION_KEY` in `.env`, or generated on first run into a key file with owner-only
  permissions, outside the database and outside git. Backups need the key; if it is lost the app
  falls back to the redacted text and says so.
- The adapter runs on the original document as well as the redacted one. Rows pair by position;
  if the row counts differ the original is not stored (fail closed, redacted text only).
- Dedup hashes stay computed on the redacted text exactly as today, so existing hashes and
  re-uploads are unaffected.
- Decrypted only inside the API process, only for: the transaction and inbox responses for the
  signed-in owner, and rule matching. It is excluded from the chat tools, the model path,
  `/privacy` previews, logs and error text; a test asserts this.
- Rows imported before this change have no original. Re-uploading the same statement attaches
  originals to existing rows without creating new ones.

### 2. Rules

- Stored per ledger: label, text, mode (`contains` or `starts_with`), direction filter
  (any, debit, credit), action, position, built-in flag.
- Matching is case-insensitive on whitespace-normalised text, against the original narration
  when present, otherwise the redacted one.
- Actions: `categorize(category)` or `transfer(account)`. A transfer posts to money-in-transit and
  is paired with the other side by the existing pairing (3-day window). If the card account has not
  been uploaded yet the row stays in the inbox as "unpaired", as today.
- Order of authority: owner's manual change on a transaction, then saved exact mappings, then
  rules by position (first match wins), then the model, then Uncategorized.
- Creating or editing a rule shows a live preview ("matches 7 transactions") and offers to apply
  it to existing Uncategorized and model-categorized rows. Rows the owner set by hand are never touched.
- "Always do this" appears when changing a transaction's category. It prefills `match_text` from
  `suggest_match_text` (the payee part with references and digits removed), editable.
- Built-in starter rules, editable and deletable: card bill payment patterns (`BPPY CC PAYMENT`,
  `BILLPAY`, `CRED`, `MB/IB PAYMENT`), cashback credits and reversals to Rewards.

### 3. Categories

- Add: Grooming (haircut, salon, spa, massage), Fitness (gym, coaching, sports), Household help
  (home cleaning, maids, Urban Company), Refunds (money in).
- Existing ledgers receive them through the existing upgrade path (`create_ledger_defaults`).
- Keywords: a few words per category. They are added to the description the model sees and
  also act as lowest-priority contains rules.
- The model prompt currently sends a refund to the merchant's own category; it changes to the
  Refunds category. Spending reports will therefore no longer net refunds against the original
  category.

### 4. Failed categorization

- Persist the categorization outcome of an upload; show a banner on the account and in the inbox
  ("12 rows not categorized: model unreachable") with a Retry button on the existing
  `/categorization/retry` endpoint. Warnings are no longer transient.

### 5. Double entry, enforced

Today a transaction is balanced only because each caller builds it that way
(`JournalRepository.add` says "the caller built it, so it already sums to zero"). Nothing stops
an unbalanced write, and this work adds new writers (rules, applying a rule to old rows, retry,
transfers). So the invariant moves into the system:

- A Postgres deferred constraint trigger on `postings` checks, at commit, that every transaction's
  postings sum to zero. It applies to every write from migration 0011 on; existing rows are not
  revalidated. A pure `verify_books(session)` function reports any existing transaction that does
  not balance, and the migration prints that count instead of failing.
- The repository's `add`, `add_posting` and `replace_posting_account` assert the same thing before
  flushing, so a bug fails in the test that causes it with a readable message.
- Rules change only the counter-posting of a transaction (same amount, opposite sign), through the
  existing `replace_posting_account`. The observed posting is never edited.
- A card-payment transfer posts the counter side to money-in-transit; pairing then merges the two
  halves, which removes both transit postings. Both steps sum to zero.
- Tests: after each of upload, retry, rule apply, recategorize, merge, pair, category merge and
  retire, `verify_books` is empty. A property test applies random sequences of these.
- Known limit: a pair needs equal and opposite amounts within 3 days. A bill payment that settles
  for a different amount (for example reward points used) stays "unpaired" in the inbox.

### 6. Redaction must not hide what classifies a row

Measured on the owner's HDFC statement: 92 of 93 narrations carry a redaction mark, but nearly all
are handles (`[VPA:..]`), references (`[ID:..]`) and account numbers. Merchant words such as
`URBAN COMPANY`, `CRED CLUB`, `APEX BADMINTON`, `SWIGGY` and the user's own note `RENT` survive.
A person payee becomes a stable per-ledger token (`[PERSON:5e31]`), which is useful: the same
person always has the same token, and the token class says "a person, not a shop".

What is lost wrongly (tested with the real redactor):

| Narration | After redaction |
|---|---|
| `UPI-SHARMA ELECTRICALS-...` | `UPI-[PERSON:d803]-...` (the business word is gone) |
| `UPI-SAGAR RATNA-...`, `POS ... SAGAR RATNA ...` | `[PERSON:..]` (a restaurant read as a person) |
| `UPI-OM SWEETS-...` | `[PERSON] SWEETS` (acceptable, still classifiable) |

Changes:

1. Redactor: card-statement merchants and `POS`/`ECOM` lines skip the given-name and surname
   lists (a card merchant is a business). In bank narrations, redact only the name words and keep
   the rest of the payee when it holds a business word; `looks_like_person` grows its business
   words (electricals, salon, gym, clinic, ratna, and so on). The table above becomes test cases,
   and a test keeps pure personal names redacted.
2. The owner's labels travel with the redacted text. When the model is asked, the prompt gets a
   block of the owner's own past decisions: masked narration, direction, and the category they
   chose, for example `UPI-[PERSON:5e31]-[VPA:19cd]-HDFC...-RENT (debit) -> Housing`. Because
   tokens are stable, one correction teaches the model that this token is the landlord. Up to
   about 20 examples, chosen by shared tokens and words with the narrations being asked, then
   most recent. They pass through the same masker as everything else, so nothing new leaves the
   machine. The system prompt says what a token means: the same token is the same counterparty.
3. Deterministic first, model last: owner override, exact mapping, rules, token lookup (a mapping
   or rule on `[PERSON:xxxx]`), owner examples with the model, then Uncategorized. The model's
   confidence threshold keeps gating its answers.
4. Optional signal: a coarse amount band (under 500, 500 to 5,000, 5,000 to 50,000, over 50,000,
   plus "round number") sent with each row, because rent and subscriptions are recognised by
   amount. Off by default, one switch in Privacy settings, since the project has so far sent no
   amounts.

Prior art: smart_importer for Beancount trains on the owner's existing ledger; firefly-bot for
Firefly III runs k-NN over labelled history with a confidence gate and re-reads the owner's
corrections to learn; Norman's engineering blog (commercial, not open source) renders per-company
corrections into a few-shot block and runs the LLM last.
Sources: https://github.com/johannesjh/smart_importer ,
https://github.com/controlol/firefly-assistant ,
https://norman.finance/de/en/blog/categorization-learns-from-corrections

## Security notes (feed the audit)

New sensitive store (sealed originals), new key handling, new user-supplied match text (no regex,
so no ReDoS), new write routes (validate and scope by ledger), new decrypted-read paths
(no logging). The final audit covers the whole repo, not only these changes.

## Left to the builder

Column and index names, migration number (next is 0011), key-file location, exact UI
layout, the suggestion heuristic's details, and test fixtures.

## Calls I made (check these)

1. Fernet with an env var or generated key file, rather than a database-level or OS keychain scheme.
2. No regex rules in the first version.
3. Order of authority puts saved exact mappings above rules.
4. Keywords interpreted as per-category words (item 5 of your list was ambiguous).
5. Refunds become their own income category instead of netting against the original spend.
6. Starter rules ship as editable rows, not hidden logic.
7. Re-upload attaches originals to old rows instead of a separate backfill tool.
8. The amount band sent to the model is off by default and switched on in Privacy settings.
9. Double entry is enforced with a Postgres constraint trigger that covers new writes only,
   plus a `verify_books` report for old data.
10. The owner's past labels reach the model as up to about 20 masked examples per request.

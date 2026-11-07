# HTTP API

Everything under `/people/{person_id}` belongs to one person's ledger. Interactive documentation is
at http://127.0.0.1:8000/docs (sign in to the cockpit first: the page needs the same session). A short tour:

```sh
API=http://127.0.0.1:8000

# create a person, add an account, finish setup
PERSON=$(curl -s -X POST $API/people -H 'Content-Type: application/json' \
  -d '{"name": "Asha Rao"}' | jq -r .id)
ACCOUNT=$(curl -s -X POST $API/people/$PERSON/accounts -H 'Content-Type: application/json' \
  -d '{"type": "savings", "institution": "HDFC Bank", "name": "HDFC Savings"}' | jq -r .id)
curl -s -X POST $API/people/$PERSON/setup/complete

# upload a statement (add -F password=... for a protected file)
curl -s -X POST $API/people/$PERSON/accounts/$ACCOUNT/uploads -F file=@statement.xls

# read the numbers
curl -s $API/people/$PERSON/reports/overview
curl -s "$API/people/$PERSON/reports/income-statement?month=2026-09"
curl -s $API/people/$PERSON/inbox
```

| Route (under `/people/{person_id}`) | Purpose |
| --- | --- |
| `GET /setup`, `POST /setup/complete` | Whether setup is done; finish it (needs an account) |
| `POST/GET /accounts`, `GET/PATCH/DELETE /accounts/{id}`, `GET /accounts/{id}/usage` | Add (`type`, `institution`, `name`, optional `opening_value_paise` and `opening_date`), list with balances, open (register, statements, holdings), rename, see what deleting removes, delete |
| `POST /accounts/{id}/value` | A new value for an account without statements |
| `GET /accounts/tree` | The books in accounting terms |
| `POST /accounts/{id}/uploads`, `DELETE /imports/{id}` | Import a statement (multipart `file`, optional `password`); remove one |
| `GET/POST /categories`, `PATCH/DELETE /categories/{id}`, `POST /categories/{id}/merge`, `POST /categories/{id}/retire` | Categories with their descriptions |
| `GET /transactions` (filters: `account_id`, `category_id`, `month`, `q`), `PATCH /transactions/{id}/category` (`account_id`), `POST /transactions/{id}/ignore` | Browse and correct |
| `GET /transactions/{id}/card-options`, `POST /transactions/{id}/card-payment` (`card_id`), `POST /transactions/{id}/card-payment/undo` (`account_id`, `origin`) | Which cards a bank row could have paid (empty when it cannot be a card payment), record it as a payment to one (the card's balance drops at once; returns `previous` so a mistake can be put back, and `matched` when the card's statement already showed it), and put it back (409 once the card's statement has matched it) |
| `POST /categorization/retry` | Categorize Uncategorized rows again |
| `GET/POST /rules`, `PATCH/DELETE /rules/{id}`, `POST /rules/reorder`, `POST /rules/{id}/apply` | Owner rules, in the order they are checked; apply one to existing rows |
| `POST /rules/preview`, `POST /rules/match-count`, `GET /transactions/{id}/rule-suggestion` | What a rule would match before you save it, and a suggested rule for a transaction |
| `GET /reports/overview`, `/reports/balance-sheet`, `/reports/income-statement`, `/reports/safe-to-spend`, `/reports/leaks`, `GET /inbox` | The figures |
| `GET/PATCH /settings` | Base amount kept aside and monthly allowance |
| `GET/PUT /privacy/terms`, `GET /privacy/preview`, `GET/PUT /privacy/labels` | Redaction controls |
| `POST /chat` | Server-sent events; send `{"message": "…"}` |

Top-level: `GET/POST /people`, `DELETE /people/{person_id}` (removes the person and their whole ledger; `204`, or `404` if unknown), `POST /sample`, `GET /catalog`, `GET /health`. Amounts are
`{"paise": 1234500, "formatted": "₹12,345.00"}`. Errors are `{"error": {"code", "message",
"hint", "detail", "correlation_id"}}` (`message` and `hint` are plain language, `detail` is the
technical reason) with one of `PARSE_FAILED`, `VALIDATION_FAILED`, `INVALID_INPUT`, `NOT_FOUND`,
`CONFLICT`, `SETUP_REQUIRED`, `CATEGORY_IN_USE`, `PASSWORD_REQUIRED`, `PASSWORD_INVALID`,
`REDACTION_FAILED`.

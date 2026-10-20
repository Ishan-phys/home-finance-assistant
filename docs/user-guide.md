# AI CFO: setup and user guide

AI CFO is a personal finance ledger that runs on your own machine. You set up the accounts you
hold, drop in their statements, and it removes personal details, reads them, sorts every
transaction into your categories, and shows what you own, what you owe, where your money went and
how much you can safely spend. You can then ask questions in plain language. Python computes every
figure. The AI only explains figures it was handed.

Under the hood it keeps double-entry books: every transaction moves money from one account to
another, and the two sides always add up. You never have to think about that, but it is why the
numbers on every screen agree with each other.

## 1. What you need

| Need | Why |
| --- | --- |
| Docker Desktop (or Docker Engine with Compose) | Runs the web app, the API, and PostgreSQL |
| An OpenAI **or** an Anthropic API key (one, not both) | Runs both the chat assistant and the statement categorizer |

The app works without keys. Without them, statements still import and every figure still computes,
but rows stay Uncategorized and the chat is unavailable. With an OpenAI key, OpenAI does both
(the Decisions API categorizes). With an Anthropic key, Claude does both.

Nothing runs in the cloud except the model calls, and those carry only redacted text (see
section 6).

## 2. Start the app

```sh
git clone <this repository> && cd home-finance-assistant
cp .env.example .env
```

Open `.env` and fill in one key (OpenAI or Anthropic, not both):

```sh
OPENAI_API_KEY=sk-...        # or: ANTHROPIC_API_KEY=sk-ant-...
```

Everything else in `.env` has a sensible default. Then:

```sh
make rebuild    # or: docker compose up --build
```

The first start builds the images, creates the database, and applies the migrations. When it
settles, open **http://127.0.0.1:3000**.

| Service | Address | Notes |
| --- | --- | --- |
| Cockpit (web app) | http://127.0.0.1:3000 | What you use |
| API | http://127.0.0.1:8000 | Used by the cockpit; `/docs` shows its schema |
| PostgreSQL | not published | Reachable only from the other containers |

Both ports bind to `127.0.0.1`, so nothing else on your network can reach the app. To check:
`./scripts/check-ports.sh`.

`make up` starts the stack without rebuilding images that already exist; `make rebuild` rebuilds after you change code. `make help` lists every shortcut. To stop: `Ctrl+C`, or `make down`. Your data lives in a Docker volume and survives a
restart. `docker compose down -v` deletes it.

### Settings in `.env`

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | none | Chat and categorization with Claude |
| `OPENAI_API_KEY` | none | Chat and categorization with OpenAI (Decisions API) |
| `CATEGORIZER` | `auto` | `auto` follows the key you set; `none` turns categorization off |
| `DECISIONS_MODEL` | `gpt-6-luna` | The model the Decisions API uses |
| `DECISIONS_THRESHOLD` | `0.6` | Labels below this confidence stay Uncategorized |
| `CATEGORIZATION_MODEL` | `claude-haiku-4-5-20251001` | The Claude fallback |
| `CHAT_MODEL` | provider default | The chat model (`claude-sonnet-5-5` or `gpt-5.5`) |
| `POSTGRES_PASSWORD` | `cfo-local-dev` | Database password (the database is not reachable from outside Docker) |

Set exactly one key. With an OpenAI key, both chat and categorization use OpenAI; with an Anthropic key, both use Claude. Setting both stops the API at start with a message asking you to remove one.

After changing `.env`, run `docker compose up -d` again so the API picks it up.

### If you upgrade from an older version

Migration `0009` moves the ledger to double-entry books. It does not convert old data: your
people, privacy terms and labels stay, but accounts and transactions are removed, so you set up
your accounts again and re-upload statements. It cannot be undone. Back up first:

```sh
make backup        # writes backup.sql (keep it private: it holds your financial data)
```

## 3. Setting up

The first time you open the app it asks for your name, and for any family names that should never
leave your machine. You can also choose **Load sample statements** to look around with invented
data instead.

Setup then takes four short steps, and the app returns to it until you finish:

1. **Welcome.** What happens next.
2. **Your accounts.** For each account you hold, pick its **type** (savings, current, cash, credit
   card, loan, fixed or recurring deposit, mutual funds, stocks, property, gold), its **bank or
   provider**, and a **name**. Where the app reads that provider's statements, it says which file
   to download. Accounts without statements (a deposit, a flat, gold, or a bank the app does not
   read yet) ask for their current value and a date instead.
3. **Your categories.** The default categories are listed with a line on what each is for. Click a
   name or description to change it, or **＋ Add category**: give it a name, say whether it is
   money going out or coming in, optionally put it inside another category, and write one line on
   what it is for. That line is also what the categorizer reads, so a clear description means
   better automatic sorting. **Use these categories** moves on.
4. **Done.** **Add your first statement** opens your first account with the upload ready.

Add more accounts or categories any time from the sidebar.

### More than one person

Each person has their own ledger; nothing is shared. **Add person** sits under the name at the top
of the sidebar, and the same place switches between people.

## 4. Getting around

The sidebar is always on the left:

| Item | What it is for |
| --- | --- |
| **Overview** | Four things: net worth, this month (earned, spent, saved), safe to spend, and the top of the Inbox |
| **Inbox** | Everything that needs you, each with its fix. The number beside it is how many |
| **Spending** | One month: what you earned, spent and saved, where it went by category, and spending that grew |
| **Transactions** | Everything that happened, searchable (press `/`), filterable by account and category |
| **Accounts** | Your accounts grouped as cash and savings, investments, deposits, other assets, and what you owe, with balances. Click one to open it |
| **All accounts** | The books in accounting terms: Assets, Liabilities, Income, Expenses and Equity |
| **Categories** | Rename, describe, add, merge, retire or delete categories |
| **Settings** | Safe-to-spend settings, privacy, and starting over |
| **Ask** | Opens the assistant on the right, beside the page |

On a phone the sidebar opens from the menu button at the top.

## 5. Statements

Open an account and choose **Upload statement**. The file is read in memory and never kept.

| Provider | What to download |
| --- | --- |
| HDFC Bank account | NetBanking statement, `.xls` or `.csv` |
| HDFC credit card | Billed statement, `.xls` or `.xlsx` |
| SBI account | Account statement, `.xlsx` or `.csv` |
| Axis credit card | Monthly statement PDF |
| Groww | Holdings statement or order history, `.xlsx` (mutual funds and stocks are separate accounts) |

A password-protected file asks for its password, which opens the file in memory and is never
stored.

What happens to a statement:

- **Every row becomes a transaction** from one place to another: "HDFC Savings → Dining", "Salary →
  HDFC Savings". The account side comes from the statement; the category is your remembered choice
  for that description, or the categorizer's, or **Uncategorized** if neither is sure.
- **Money between your own accounts pairs up.** A card bill paid from savings shows on both
  statements. Once both are uploaded the two halves become one transfer, "HDFC Savings → HDFC
  Card", which is neither income nor spending. Until the other side arrives it waits in the Inbox.
- **The closing balance is checked.** The first statement for an account sets its starting balance
  so the figures match the bank. Later statements are checked against the books; a mismatch means a
  statement is missing, and the Inbox says by how much.
- **Uploading the same file twice adds nothing**, and overlapping statements add only the new rows.
- Holdings statements record what your investments are worth; order files record what you paid.

The upload summary says how many rows were added, how many were already there, how many matched a
movement from another account, and how many need a category.

**Removing a statement** (account page, **Statements** tab, **Remove**) takes out its rows and its
balance. A transfer it completed goes back to waiting for its other side.

## 6. The Inbox

| Item | What to do |
| --- | --- |
| **Needs a category** | **Choose category**. The choice is remembered for the same description in later statements, and applied to other rows like it |
| **Left … for an account of yours** / **Arrived in … from an account of yours** | Upload the statement of the other account. If it is not one of your accounts, choose a category instead |
| **… is short of its statement** | A statement is missing for that period. Upload it |
| **Card bill … is due** | Shows until a payment to the card appears after the statement date |

## 7. The figures

- **Net worth** is everything you own minus everything you owe. Credit card balances and loans
  reduce it. Investments count at their latest market value.
- **Earned, spent, saved** cover one month. Money to and from friends and family, and cashback, are
  shown on their own lines rather than counted as salary or lifestyle spending.
- **The check line** on Spending reads "Net worth changed by … : saved … ✓". It proves the month's
  figures agree with the change in what you own; revaluations and opening balances are listed when
  they play a part.
- **Safe to spend** is your cash and savings, minus the base amount you keep aside, minus what you
  owe on credit cards, capped by your monthly allowance if you set one. **How is this worked out?**
  on the Overview shows each step. Set the base amount and allowance in **Settings**.
- **Deposits, property and gold** change only when you **Update value** on their page. The change
  counts toward net worth, not income.
- **Transactions** open to a **Bookkeeping** panel showing every side of the transaction and where
  each came from (the statement, the categorizer, or you). **Ignore this row** drops a duplicate
  for good.

## 8. Privacy: what is stored and what is sent

Before a statement is parsed, a redactor removes personal details: names, addresses, phone numbers,
email, PAN, account and card numbers, and UPI handles. Each becomes a stable token such as
`[PERSON:ab12]`. The same payee always gets the same token, so grouping and de-duplication still
work. The original file is never kept, and tokens cannot be turned back into the details.

Amounts, dates, and merchants stay readable. For UPI, IMPS, and NEFT, the other party's name is
redacted when it looks like a person and kept when it looks like a business.

Redaction is best-effort. In **Settings**, the privacy section has:

- **Always redact**: your own names. Add any name that should never appear, one per line.
- **Preview**: each recent description as stored and as it would be sent to a model.
- **Names for redacted people and numbers**: give a token a name such as "Landlord". The name
  appears only to you. A model only ever sees the token.

Your account names, institutions and the names of categories you created are swapped for aliases
before anything reaches a model, and the assistant's replies are shown with your names put back.

Two things leave your machine: redacted statement lines (and your category descriptions) to the
categorizer, and figures with aliases to the chat model. Consider asking your provider to enable
zero data retention. The app has no login; it relies on binding to `127.0.0.1`.

## 9. Asking questions

**Ask** opens the assistant beside the page. It reads your ledger through five tools (net worth,
spending, spending that grew, safe to spend, and the Inbox) and explains what they returned. Try:

- "How much can I safely spend this month?"
- "Where did my money leak this month?"
- "What is my net worth, and what do I owe?"

Every figure comes from a tool result, not from the model's arithmetic. History lasts until the API
restarts.

## 10. A typical month

| When | What to do |
| --- | --- |
| Start of the month | Upload last month's bank and card statements |
| After uploading | Clear the Inbox: categorize what is new, upload any missing other side |
| Any time | Update the value of deposits or property; adjust categories |
| Mid-month | Check Safe to spend on the Overview |

You do not need to upload everything at once, or in order.

## 11. Troubleshooting

| Problem | Likely cause and fix |
| --- | --- |
| The page is blank or errors on load | `docker compose ps` shows whether all three services are up. `docker compose logs api` shows startup errors, including a failed migration |
| "Add an account first" | Statements go into an account. Finish setup or add one from the sidebar |
| "This file doesn't look like a … statement" | The file is not the format for that account. The message says what to upload instead |
| `PASSWORD_REQUIRED` / `PASSWORD_INVALID` | The file is protected. Enter the right password when asked |
| `REDACTION_FAILED` | A file could not be redacted, so nothing was imported by design. Report it with the bank and file type |
| Everything needs a category | No key is set, the key is invalid, or the categorizer is unreachable (`docker compose logs api` shows the provider's error). Fix `.env`, restart, then categorize by hand or retry |
| A transfer between my accounts did not pair | Upload the other account's statement for the same days. If both are uploaded, set the row's category to **Own account or investment** |
| "… is short of its statement" | A statement for that account is missing between two uploaded ones |
| "Add a category" is refused | Names must be unique, and every category needs a line on what it is for |
| A category cannot be deleted | It has transactions. Merge it into another instead |
| Chat says the assistant is unavailable | Neither `ANTHROPIC_API_KEY` nor `OPENAI_API_KEY` is set, or the key is invalid |
| Port 3000 or 8000 is already in use | Stop what is using it, or change the port mapping in `docker-compose.yml` |

## 12. For developers

### Run the tests

```sh
uv sync                              # one workspace, Python 3.13
uv run pytest                        # starts a throwaway PostgreSQL via Docker
uv run ruff check . && uv run mypy packages/*/src api/src tools/check_imports.py
uv run python tools/check_imports.py # package boundaries
./tools/test_isolated.sh             # each library passes alone
```

Browser tests need the stack running. They empty the database first, so never point them at data you
want to keep:

```sh
docker compose up -d --build
cd web && npm ci && npx playwright install chromium && npx playwright test
```

`./scripts/check-ports.sh` verifies that PostgreSQL has no host port and that the web app and API
listen on `127.0.0.1` only.

### Layout

A `uv` workspace of small packages under `packages/`, the API in `api/`, and the cockpit in `web/`.
Each package states what it may depend on, and CI enforces it. See the README for the table.

### Database migrations

```sh
cd packages/cfo-ledger
export DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
uv run alembic upgrade head
uv run alembic current
```

Compose runs `alembic upgrade head` when the API starts.

### Using the API directly

Everything under `/people/{person_id}` belongs to one person's ledger. Interactive documentation is
at http://127.0.0.1:8000/docs. A short tour:

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
| `POST /categorization/retry` | Categorize Uncategorized rows again |
| `GET /reports/overview`, `/reports/balance-sheet`, `/reports/income-statement`, `/reports/safe-to-spend`, `/reports/leaks`, `GET /inbox` | The figures |
| `GET/PATCH /settings` | Base amount kept aside and monthly allowance |
| `GET/PUT /privacy/terms`, `GET /privacy/preview`, `GET/PUT /privacy/labels` | Redaction controls |
| `POST /chat` | Server-sent events; send `{"message": "…"}` |

Top-level: `GET/POST /people`, `POST /sample`, `GET /catalog`, `GET /health`. Amounts are
`{"paise": 1234500, "formatted": "₹12,345.00"}`. Errors are `{"error": {"code", "message",
"hint", "detail", "correlation_id"}}` (`message` and `hint` are plain language, `detail` is the
technical reason) with one of `PARSE_FAILED`, `VALIDATION_FAILED`, `INVALID_INPUT`, `NOT_FOUND`,
`CONFLICT`, `SETUP_REQUIRED`, `CATEGORY_IN_USE`, `PASSWORD_REQUIRED`, `PASSWORD_INVALID`,
`REDACTION_FAILED`.

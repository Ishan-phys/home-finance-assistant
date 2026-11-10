# Troubleshooting and FAQ

Find the stage where you are stuck. Each entry says what you see, why, and what to do. If you
are not sure where to start, run these two commands from the app's folder and read the result:

```sh
docker compose ps
docker compose logs --tail 50 api
```

`ps` shows whether the three services (`db`, `api`, `web`) are running. The log shows the app's
own explanation when something fails.

**Contents:** [The app will not start](#the-app-will-not-start) ·
[Signing in](#signing-in) · [Setup](#setup) · [Uploading statements](#uploading-statements) ·
[The Inbox and categories](#the-inbox-and-categories) ·
[Figures that look wrong](#figures-that-look-wrong) · [The assistant](#the-assistant) ·
[Data and backups](#data-and-backups) · [Getting help](#getting-help) · [FAQ](#faq)

---

## The app will not start

| What you see | Why, and what to do |
| --- | --- |
| `docker: command not found` or "not recognized" | Docker is not installed, or the terminal was opened before it was. Install Docker, then close and reopen the terminal |
| An error mentioning the "daemon" or a "pipe" | Docker Desktop is not running. Start it and wait until the whale icon settles |
| "port is already allocated" or "address already in use" | Another program is using port **3000** or **8000**. Stop it, then run `docker compose up -d` again |
| The page at <http://127.0.0.1:3000> does not load | The app is still starting (give it a minute), or a service stopped. Run `docker compose ps`. If a service is not running, read `docker compose logs api` and `docker compose logs web` |
| The `api` log says **"both OPENAI_API_KEY and ANTHROPIC_API_KEY are set; set only one in .env"** | You set two model keys. Remove one from `.env` and run `docker compose up -d` |
| `docker compose ps` shows `api` restarting, or the log shows a **migration** error | The database could not be updated. Read the last lines of `docker compose logs api` and see [Getting help](#getting-help) |
| The first start takes a very long time | The first build downloads a lot. Several minutes is normal. Later starts take seconds |
| The build fails while downloading | Your connection dropped or blocked a download. Run `docker compose up -d --build` again |
| You changed `.env` and nothing changed | Run `docker compose up -d`. Changes are only read when you do |

## Signing in

| What you see | Why, and what to do |
| --- | --- |
| **"That username or password is not right."** | The username must match `OWNER_USERNAME` in `.env`. The password is the one you typed when you made the hash, **not** the hash itself |
| **"Too many failed sign-in attempts. Wait 15 minute(s) and try again."** | Five wrong attempts lock the form for 15 minutes, even for the right password. Wait, then try again |
| **"Sign-in is not set up: OWNER_USERNAME and OWNER_PASSWORD_HASH must be set in .env"** | One of those lines is empty. Fill it in, then `docker compose up -d` |
| **"Sign-in is not set up: SESSION_SECRET must be at least 32 characters"** | The secret is empty or too short. Make a longer one (step 4b in [Getting started](getting-started.md#4b-make-the-session-secret)) |
| **"Cannot reach the app. Check that Tailscale is connected, then try again."** | The page cannot reach the API. Ignore the Tailscale part unless you use it. Check that `docker compose ps` shows all three services running |
| **I know my password is right, but sign-in still fails** | The hash was probably damaged when you pasted it. It must be in **single quotes** and complete. Make a new one (see below) |

### I forgot my password

There is no recovery email, because nothing is stored outside your computer. You own the `.env`
file, so you make a new password:

```sh
docker compose run --rm --no-deps api python -m cfo.api.auth
```

Paste the new `scrypt$…` line over `OWNER_PASSWORD_HASH` in `.env` (keeping the single quotes) and run
`docker compose up -d`. Your data is untouched.

### I sign in but land back on the sign-in page

You are signed in, but your browser did not keep the sign-in. The app sets a "secure" cookie by
default. Some browsers, Safari most often, refuse to keep a secure cookie on a plain
`http://` address, even for `127.0.0.1`.

If this is your case, and you only ever open the app at `http://127.0.0.1:3000` on your own
computer:

1. Set `SESSION_COOKIE_SECURE=false` in `.env`.
2. Run `docker compose up -d`.
3. Sign in again.

Do not turn this off if you reach the app through a network.

### "Invalid host header" or the page works on one address but not another

The app only answers to names it knows: `localhost`, `127.0.0.1` and its own services. If you open
it by another name (for example through a private network), add that name to `ALLOWED_HOSTS` in
`.env` and run `docker compose up -d`. See [Using it from another
device](configuration.md#using-it-from-another-device).

## Setup

| What you see | Why, and what to do |
| --- | --- |
| The app keeps sending you to the setup screens | Setup is not finished. Add at least one account, then follow it to **Add your first statement** |
| **"Add an account first"** | Statements go into an account. Finish setup, or add one with **+** next to **Accounts** in the left menu |
| My bank is not in the **Bank or provider** list | Choose **Something else** and type its name. The account then needs its value entered by hand. See [Accounts without statements](statements.md#accounts-without-statements) |
| I added an account twice | Open it and choose **Delete account**. The dialog says what goes with it |
| I want to change a category | Open **Categories** and click the name or description. You can also merge, retire or delete one |
| **"Add a category" is refused** | Names must be unique, and every category needs a line saying what it is for |
| A category cannot be deleted | It has transactions. **Merge** it into another instead |
| I want to start again | **Delete person** removes one person's books. See [Starting over](configuration.md#starting-over) |

## Uploading statements

Most problems here come with a clear message. Find it in the table in
[When an upload is refused](statements.md#when-an-upload-is-refused). The usual causes:

- **You chose the wrong account** for the file. The message says which file the account expects.
- **The file was edited and re-saved.** Download it again and use it exactly as the bank gave it.
- **The file is password-protected.** Enter the password in the box that appears.
- **A statement is missing.** If a warning says the balance does not match, upload the month
  before.

| What you see | Why, and what to do |
| --- | --- |
| **"categorization skipped: no model is configured"** | You have no model key. Rows are Uncategorized and wait in the Inbox for you. See [Getting started, step 5](getting-started.md#step-5-decide-about-a-model-key-optional) |
| Nothing seems to happen after I choose **Upload** | Wait a moment, since a long file takes time. If a **File password** box appeared, enter the password and choose **Upload** again |
| **0 rows added**, **"already there"** | You uploaded the same period before. Nothing new was added, which is correct |
| **"this statement's card or account number differs from earlier ones"** | The file may belong to a different account. If it does, remove it (**Statements** tab, **Remove**) and upload it into the right account |

## The Inbox and categories

| What you see | Why, and what to do |
| --- | --- |
| Everything needs a category | You have no model key, the key is not valid, or the provider could not be reached (`docker compose logs api` shows its error). Fix `.env`, run `docker compose up -d`, then sort rows yourself, or write rules |
| **"Left … for an account of yours; upload the other side"** | Money moved between your accounts, but only one side is uploaded. Upload the other account's statement. If it was not a move between your accounts, **Choose category** instead |
| A transfer between my accounts did not pair | Upload the other account's statement for the same days. If both are uploaded, set the row's category to **Own account or investment** |
| A bank payment to a credit card is stuck | Click **Pay a card** on the row and pick the card. See [Paying a credit card](user-guide.md#paying-a-credit-card) |
| **"Card bill … is due"** will not go away | It stays until payments to the card since its statement date cover the bill. Upload your bank statement with the payment, or use **Pay a card** |
| **"… is short of its statement"** | A statement is missing between two you uploaded. Upload it |
| I chose the wrong category | Open the row's category button and pick another. For a card payment, use **Undo** in the message at the bottom within 45 seconds, or pick the right card |
| A rule did not apply | Rules run from the top and the first match wins. A rule never changes a transaction you set by hand. Check the order on the **Rules** page |

## Figures that look wrong

| What you see | Why, and what to do |
| --- | --- |
| **Overview shows a month with almost nothing in it** | The Overview and Spending show the current month once it has any statements, even a few rows. Use the arrows beside the month name on **Spending** to move to the month you want, and upload the rest of the current month when it ends |
| **Net worth looks too low or too high** | An account is missing, a statement is missing, or a by-hand account has an old value. Check each account's balance, and use **Update value** on deposits, property and gold. Investments count at the value in the latest holdings file you uploaded |
| **Safe to spend is much lower than my cash** | It subtracts your base amount (Settings) and what you owe on credit cards. Click **How is this worked out?** to see each step. Lower the base amount in **Settings** if it is too cautious |
| **Safe to spend is zero** | Your cash is less than the base amount plus your card balances |
| **A card bill counted as spending** | The payment and the card statement are not joined yet. Upload both statements, or use **Pay a card** |
| **Spending on a page differs from what I expected** | Check the month. Money moving between your own accounts is not spending, and opening balances are not payments |
| **The "check" line on Spending shows a difference** | The month's figures do not add up to the change in net worth. Look at the Inbox for a missing statement or an uncategorized row |

## The assistant

| What you see | Why, and what to do |
| --- | --- |
| **"the assistant could not answer"** | No model key is set, the key is not valid, or the provider cannot be reached. Check `.env`, run `docker compose up -d`, and read `docker compose logs api` for the provider's own message |
| The assistant forgot what we were talking about | The conversation clears when you close the panel or restart the app. Keep the panel open while you follow up |
| It says it cannot search for a person | Names are hidden from it for privacy. Use the search box on **Transactions** |
| It says there is nothing to analyse | No statements are uploaded for that period |
| A name like `Credit_Or_Loan_2` appears | A stand-in for one of your accounts. Ask again and name the kind of account |
| A figure differs from a page | Check which period the assistant used. It says. See [the assistant guide](assistant.md) |

## Data and backups

| What you see | Why, and what to do |
| --- | --- |
| My data disappeared after a restart | Stopping or restarting never deletes data. `docker compose down -v` and `make reset` do. If you ran either, restore from a [backup](configuration.md#restore-from-a-backup) |
| Original bank text is missing, and only cleaned text shows | The narration key is gone. Without it the app falls back to the cleaned text. [Back the key up](configuration.md#also-back-up-the-narration-key) |
| I changed folders or reinstalled and my data is gone | The data belongs to the Docker volume, named after the folder. Use the same folder name, or restore from a backup |

## Getting help

If you are still stuck, [open an issue](https://github.com/Ishan-phys/home-finance-assistant/issues).
Include:

- What you did, what you expected, and what happened.
- The output of `docker compose ps`.
- The last lines of `docker compose logs --tail 100 api`, **after reading them over** to remove
  anything personal.

**Never attach** your `.env` file, a statement, `backup.sql`, or a screenshot showing your real
accounts or balances. They hold your financial data and keys.

## FAQ

**Does it connect to my bank?**
No. You download statements from your bank yourself and upload them. The app never asks for your
bank login.

**Is my data uploaded anywhere?**
Your ledger stays on your computer. The only thing that leaves it is text for the model, if you
set a key: redacted statement lines (to sort them) and figures with stand-in names (for the
assistant). Your name, account and card numbers, phone numbers and UPI handles are removed first.
See [Privacy](user-guide.md#privacy-what-is-stored-and-what-is-sent).

**Do I need a model key?**
No. Without one, everything works except the assistant, and you sort transactions yourself (rules
help). See [Getting started, step 5](getting-started.md#step-5-decide-about-a-model-key-optional).

**Do I need an internet connection?**
Only to install and update, and for the model if you use one. Reading statements, the books and
every page work offline.

**Which banks work?**
HDFC Bank (accounts and credit cards), SBI accounts, Axis credit cards, and Groww (mutual funds
and stocks). Any other account can be tracked by entering its value by hand. See
[Statements](statements.md).

**Can two people use it?**
Yes. Each person has their own separate books. Use **Add person** in the left menu, and switch
between them in the same place. Nothing is shared.

**Can I use it on my phone?**
The layout works on a phone. Reaching the app from a phone needs a private network. See
[Using it from another device](configuration.md#using-it-from-another-device).

**Is the currency always rupees?**
Yes. All amounts are in rupees.

**Is the assistant giving financial advice?**
No. It explains your own numbers and describes habits. It does not give tax, legal or investment
advice and never recommends a security.

**How do I delete everything?**
To remove one person, use **Delete person**. To remove all data, back up if you want to keep
anything, then run `docker compose down -v`.

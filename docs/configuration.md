# Configuration and running the app

This page is the reference for everything in your `.env` file, and for the everyday jobs of
keeping the app running: stopping and starting it, changing your password, backing up, restoring,
and updating. For a first-time walkthrough, see [Getting started](getting-started.md).

## Changing a setting

All settings live in the file called `.env` in the app's folder. To change one:

1. Open `.env` in a plain text editor (`notepad .env` on Windows, `open -e .env` on macOS,
   `nano .env` on Linux).
2. Change the line and save.
3. Apply it:

```sh
docker compose up -d
```

Restarting alone is not enough. `docker compose up -d` is what makes the app read `.env` again.

## Every setting

| Setting | Default | What it does |
| --- | --- | --- |
| `OWNER_USERNAME` | none | The username you sign in with |
| `OWNER_PASSWORD_HASH` | none | The scrambled form of your password. Keep it in single quotes. See [Sign-in](#sign-in) |
| `SESSION_SECRET` | none | At least 32 random characters. Keeps your signed-in session safe |
| `SESSION_COOKIE_SECURE` | `true` | Leave as `true`. See [Sign-in is not working](troubleshooting.md#i-sign-in-but-land-back-on-the-sign-in-page) before changing it |
| `OPENAI_API_KEY` | none | Use OpenAI for both chat and sorting transactions |
| `ANTHROPIC_API_KEY` | none | Use Claude for both chat and sorting transactions |
| `CATEGORIZER` | `auto` | `auto` follows the key you set. `none` turns automatic sorting off |
| `DECISIONS_MODEL` | `gpt-6-luna` | The OpenAI model that sorts transactions |
| `DECISIONS_THRESHOLD` | `0.6` | A label below this confidence is left Uncategorized for you |
| `CATEGORIZATION_MODEL` | `claude-haiku-4-5-20251001` | The Claude model that sorts transactions |
| `CHAT_MODEL` | empty | The assistant's model. Empty means the provider's default (`claude-sonnet-5-5` or `gpt-5.5`) |
| `NARRATION_KEY` | generated | The key that encrypts the original bank text of each row. See [Backups](#back-up-your-data) |
| `ALLOWED_HOSTS` | empty | Extra names the app answers to. See [Using it from another device](#using-it-from-another-device) |
| `POSTGRES_PASSWORD` | `cfo-local-dev` | The database password. The database cannot be reached from outside Docker, so the default is fine |

You can leave anything you do not recognise at its default.

## Model keys

The model does two jobs: it **sorts transactions** into categories as you upload, and it
**answers your questions** in the Ask panel. Python computes every figure regardless.

- **Set exactly one key**, either `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`. With an OpenAI key, OpenAI
  does both jobs. With an Anthropic key, Claude does both.
- **Setting both stops the app from starting.** The log says *"both OPENAI_API_KEY and
  ANTHROPIC_API_KEY are set; set only one in .env"*. Remove one and run `docker compose up -d`.
- **No key** is fine. Statements import and every figure works. Rows stay Uncategorized until you
  sort them (or write rules), and the Ask assistant cannot answer.
- To **switch provider**, remove the old key, add the new one, and run `docker compose up -d`.
- To turn automatic sorting off while keeping chat, set `CATEGORIZER=none`.

An API key is not the same as a chat subscription. Create one in your provider's developer
console: <https://platform.openai.com/api-keys> for OpenAI, <https://console.anthropic.com/> for
Anthropic. Providers charge per use. Treat the key like a password.

What is sent to the provider is described in
[Privacy](user-guide.md#privacy-what-is-stored-and-what-is-sent).

## Sign-in

Only you can sign in. The app keeps a scrambled hash of your password, never the password.

- **You stay signed in on a browser for 5 days.** **Sign out** is at the bottom of the left menu.
- **Five wrong passwords in 15 minutes lock the form for 15 minutes**, even for the right
  password.

### Change your password

1. Make a new hash:

   ```sh
   docker compose run --rm --no-deps api python -m cfo.api.auth
   ```

   Choose a password of at least 12 characters. Copy the line that starts `scrypt$`.
2. Replace the `OWNER_PASSWORD_HASH` line in `.env`, **keeping the single quotes**.
3. Run `docker compose up -d`.

Everyone signed in is signed out, and you sign in with the new password.

### A device was lost or stolen

Signing out clears the sign-in on that one browser only. A copy of the sign-in cookie stays valid
until it expires. To cut off every device at once, change `SESSION_SECRET` to a new random string
(for example the output of `docker compose run --rm --no-deps api python -c "import secrets;
print(secrets.token_urlsafe(48))"`), then run `docker compose up -d`. Changing the password hash
does the same.

## Using it from another device

By default only the computer running the app can open it: the web page (port 3000) and the API
(port 8000) both listen on `127.0.0.1`. That is deliberate. Your finances should not be visible
to everyone on your network.

To reach it from your phone or another computer, use a **private network** such as Tailscale, and
add the name you use in the browser to `ALLOWED_HOSTS`, for example
`ALLOWED_HOSTS=cfo.your-tailnet.ts.net`, then run `docker compose up -d`. The app refuses requests
for names it does not know, which stops a malicious website from talking to it.

**Never publish the API port (8000) to the internet or to a shared network.** The sign-in is
designed to protect an app that only you can reach.

## Your data

Everything is stored in two Docker **volumes** on your computer.

| Volume | What it holds |
| --- | --- |
| `dbdata` | Your whole ledger: accounts, transactions, rules, settings |
| `keys` | The key that encrypts the original bank text of each row |

They survive stopping and starting the app. They are **deleted** by `docker compose down -v` and
by `make reset`, and by deleting them in Docker Desktop. If you only mean to remove one person,
use **Delete person** in the app instead.

## Back up your data

Back up before you update the app and now and then in between.

```sh
docker compose exec -T db pg_dump -U cfo -f /tmp/backup.sql cfo
docker compose cp db:/tmp/backup.sql backup.sql
```

These two commands work the same on Windows, macOS and Linux. (On macOS and Linux, `make backup`
does the same job in one step.)

**You should see** a file called `backup.sql` in the app's folder, and no error.

> **`backup.sql` contains your financial data.** Keep it private, store it somewhere safe, and
> never email it or put it in a public place.

### Also back up the narration key

Each row's original bank text is stored **encrypted**, so you can see what a row is. The key to
read it is **not** in the database backup. Without it the app falls back to the cleaned text.
Copy the key out and keep it with your backup:

```sh
docker compose exec api cat /keys/narration.key
```

Alternatively set `NARRATION_KEY` in `.env` yourself, so you hold the key. Generate one with
`docker compose run --rm --no-deps api python -c "from cfo.vault import generate_key;
print(generate_key())"`.

## Restore from a backup

> **This replaces everything currently in the app.** Do it only to recover, or to move to a new
> computer. It is an advanced step.

1. Stop the app and remove the old database volume:

   ```sh
   docker compose down
   docker volume ls          # find the volume whose name ends in _dbdata
   docker volume rm NAME_dbdata
   ```

2. Start only the database, and wait a few seconds:

   ```sh
   docker compose up -d db
   ```

3. Load the backup:

   ```sh
   docker compose cp backup.sql db:/tmp/backup.sql
   docker compose exec -T db psql -U cfo -d cfo -f /tmp/backup.sql
   ```

4. Put the narration key back, if you use a new `keys` volume: set `NARRATION_KEY=` in `.env` to
   the key you saved.
5. Start everything: `docker compose up -d`.

## Update to a newer version

1. Back up ([above](#back-up-your-data)).
2. Get the new code and rebuild:

   ```sh
   git pull
   docker compose up -d --build
   ```

   (If you downloaded a ZIP, download the new ZIP, unzip it into a folder with the **same name**
   as before so it finds your existing data, copy your `.env` into it, and run the second command
   there.)
3. The app updates your database automatically when it starts.

Check [`database-migrations.md`](database-migrations.md) before updating from a much older version:
one old upgrade (`0009`) removed accounts and transactions and asked you to set up again.

## Starting over

- **Remove one person and their books:** use **Delete person** in the left menu. Nobody else's
  books change.
- **Erase everything:** this deletes every ledger on your computer. Back up first, then
  `docker compose down -v`. The next start asks for a name again.

## Commands

Where a `make` shortcut exists (macOS and Linux), it does the same as the Docker command.

| To | Docker command | Shortcut |
| --- | --- | --- |
| Start | `docker compose up -d` | `make up` |
| Start after changing code, or the first time | `docker compose up -d --build` | `make rebuild` |
| Stop, keeping data | `docker compose stop` | `make stop` |
| Stop and remove the containers, keeping data | `docker compose down` | `make down` |
| See what is running | `docker compose ps` | `make ps` |
| Read the logs | `docker compose logs -f api` | `make logs s=api` |
| Back up | `docker compose exec -T db pg_dump -U cfo -f /tmp/backup.sql cfo`, then `docker compose cp db:/tmp/backup.sql backup.sql` | `make backup` |
| **Erase everything** | `docker compose down -v` | `make reset` |
| List all shortcuts | | `make help` |

## Ports

| Service | Address | Notes |
| --- | --- | --- |
| The app (what you use) | <http://127.0.0.1:3000> | |
| The API | <http://127.0.0.1:8000> | Used by the app. Every request except `/health` needs you signed in |
| The database | not published | Reachable only by the other containers |

If something else on your computer already uses port 3000 or 8000, stop that program. To check
that only your own computer can reach the app, run `./scripts/check-ports.sh`.

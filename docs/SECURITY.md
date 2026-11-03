# Security and privacy

This project processes bank and card statements, so security and privacy reports matter.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem or a privacy leak. Use GitHub's
private vulnerability reporting ("Security" tab, then "Report a vulnerability") on this
repository. Include steps to reproduce using **synthetic data only**. Do not attach real
statements, keys or personal details.

We aim to acknowledge a report within a week and to say how we will handle it soon after.

## What is in scope

- Personal details that survive redaction and reach the database or a model request.
- Access across people or ledgers (isolation failures).
- Secrets or personal data in the repository, logs, or error messages.
- Anything that makes the app reachable beyond `127.0.0.1` by default.
- Injection, unsafe file parsing, or password handling on uploaded statements.

## Things to know before using it with real data

- **Redaction is best-effort.** It removes names, phone numbers, account and card numbers, and
  similar details using patterns, lists and the shape of payment narrations. A person whose name
  looks like a business, or an unusual nickname on no list, can get through. The Privacy card
  previews exactly what would be sent so you can add terms for anything missed.
- **Models see redacted text only**, but they do see merchants, amounts and dates. If you enable
  OpenAI's Decisions API or Anthropic's API, those providers receive that redacted text. Check
  your account's data-retention settings.
- **The app is a single-household tool with one owner sign-in.** Every API route except `/health`
  and the sign-in routes needs a valid session cookie. The password is stored only as a salted
  scrypt hash (`OWNER_PASSWORD_HASH`), sessions last 5 days, and repeated wrong passwords lock the
  form for 15 minutes. The app binds to `127.0.0.1` and refuses requests whose `Host` or browser
  `Origin` is not this machine or the web service (`ALLOWED_HOSTS` extends the list). Sessions are
  signed cookies with no server-side record, so signing out clears the browser's copy only; to
  end every session, change `SESSION_SECRET`. This is a single-owner sign-in, not a multi-user
  system, and it has no second factor. Put a network in front of it (for example Tailscale) rather
  than the open internet.
- **Original narrations are encrypted, the rest of the database is not.** The unredacted bank text
  is sealed with a key (`NARRATION_KEY`, or a generated file in a Docker volume), so a leaked
  database dump shows ciphertext. Anyone with access to the host can read both the key and the
  database, so use full-disk encryption. `make backup` covers the database only: back the key up
  with it, because a lost key falls back to the redacted text.
- **Uploads are capped** at 10 MiB and 20,000 rows, and the file type is checked from its bytes.
  The expanded size of an `.xlsx` is not limited.
- **Statement text is untrusted input to the model.** The categorizer accepts only a category it
  offered for that line, and the chat tools are read-only, so the worst outcome is a wrong
  category.
- **Statement passwords** are used in memory to open a file and are never stored or logged.
- **Back up before upgrading**: migration `0006` is one-way.

## Keys

API keys go in `.env`, which is gitignored. Never commit one. If you do by mistake, revoke it at
the provider first, then remove it from history.

## Dependencies

Dependency review blocks a pull request that adds a package with a known advisory, and a weekly
audit checks what is already locked. Advisories that do not apply here are listed with their
reasons in `.github/pip-audit-ignore.txt`.

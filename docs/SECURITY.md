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
- **The app is a single-user local tool.** There is no login. It binds to `127.0.0.1`; do not
  expose it to a network.
- **The database is not encrypted at rest** by the app. Use full-disk encryption.
- **Statement passwords** are used in memory to open a file and are never stored or logged.
- **Back up before upgrading**: migration `0006` is one-way.

## Keys

API keys go in `.env`, which is gitignored. Never commit one. If you do by mistake, revoke it at
the provider first, then remove it from history.

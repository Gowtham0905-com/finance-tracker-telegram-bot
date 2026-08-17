# Personal Finance Tracker — Telegram Bot + SQL Backend + Analytics Dashboard

An end-to-end personal finance tracker: log income and expenses by texting a Telegram bot, backed by a SQL Server database, with a web dashboard for analytics and reporting.

## Architecture

```
Telegram Bot (Python) ──┐
                         ├──► SQL Server (Users, Expenses, Income)
FastAPI Web App ─────────┘         ▲
        │                          │
        └──► REST API (JWT auth) ──┘
        │
        └──► Dashboard (HTML/JS/Chart.js)
```

- **`bot.py`** — Telegram bot. Handles signup (name → unique login ID → password), daily expense/income logging via natural-language messages (`food 250`, `+salary 20000`), and a date picker for backdating entries.
- **`webapp/`** — FastAPI backend + static frontend. JWT-authenticated REST API serving user-scoped financial summaries, category breakdowns, trend data, and CSV report exports. Dashboard built with Chart.js.
- **SQL Server** — normalized schema (`Users`, `Expenses`, `Income`) with foreign-key relationships and a unique constraint on login IDs.

## Features

- Natural-language expense/income logging via Telegram (`food 250` = expense, `+salary 20000` = income)
- Backdated entries via an inline calendar picker
- Multi-user support — each Telegram user gets isolated data via `UserID`
- Website login shares credentials set up through the bot (Argon2-hashed passwords, JWT sessions)
- Dashboard: income/expense/balance totals, category breakdown (donut chart), monthly *and* daily trend views, recent transactions
- Custom date-range filtering across the whole dashboard
- CSV report exports (transactions and summary), respecting the active date filter
- Structured error handling and logging on both the bot and API side

## Tech stack

Python · python-telegram-bot · FastAPI · SQL Server (T-SQL) · pyodbc · JWT (python-jose) · Argon2 (passlib) · Chart.js · vanilla JS/HTML/CSS

## Setup

### 1. Database
Run `webapp/migration.sql` against your SQL Server instance (adds `LoginID` and `PasswordHash` columns to an existing `Users` table — adjust if starting from scratch).

### 2. Bot
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your bot token and DB details
python bot.py
```

### 3. Website
```bash
cd webapp
pip install -r requirements.txt
cp .env.example .env   # fill in your DB details and a generated JWT secret
uvicorn main:app --reload
```
Visit `http://localhost:8000`.

## What I learned building this

- **Local dev and production are different problems.** The database originally used Windows Authentication, which only works because everything ran on one PC — deploying anywhere else meant rethinking auth and connectivity from scratch.
- **Schema decisions echo through every layer.** Splitting "display name" from "unique login ID" after the fact touched the bot's signup flow, the database queries, and the API auth layer simultaneously.
- **Secrets management isn't optional.** Moved from hardcoded credentials to environment variables (`.env`, gitignored) before this became public — a good habit to build early rather than retrofit.

## Roadmap

- [ ] Containerize (Docker) for consistent deployment
- [ ] Move off local SQL Server to a cloud-hosted database
- [ ] Deploy bot + website to run 24/7 independent of any single machine
- [ ] `/resetpassword` command for the bot

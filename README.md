# Personal Finance Tracker — Telegram Bot + SQL Backend + Analytics Dashboard

An end-to-end personal finance tracker: log income and expenses by texting a Telegram bot, backed by a PostgreSQL database, with a web dashboard for analytics and reporting. Deployed and live 24/7 on Render.

## Architecture

```
Telegram Bot (Python) ──┐
                         ├──► PostgreSQL / Supabase (Users, Expenses, Income)
FastAPI Web App ─────────┘         ▲
        │                          │
        └──► REST API (JWT auth) ──┘
        │
        └──► Dashboard (HTML/JS/Chart.js)
```

Both the bot and the web app run as a single FastAPI service — the bot's polling loop starts as an async background task when the web server boots, so one Render deployment covers both.

- **`webapp/bot.py`** — Telegram bot. Handles signup (name → unique login ID → password), daily expense/income logging via natural-language messages (`food 250`, `+salary 20000`), and a date picker for backdating entries.
- **`webapp/`** — FastAPI backend + static frontend. JWT-authenticated REST API serving user-scoped financial summaries, category breakdowns, trend data, and CSV report exports. Dashboard built with Chart.js.
- **PostgreSQL (Supabase)** — normalized schema (`Users`, `Expenses`, `Income`) with foreign-key relationships and a unique constraint on login IDs. Connected via Supabase's connection pooler (Supavisor) for IPv4 compatibility with standard cloud hosts.

## Features

- Natural-language expense/income logging via Telegram (`food 250` = expense, `+salary 20000` = income)
- Backdated entries via an inline calendar picker
- Multi-user support — each Telegram user gets isolated data via `UserID`
- Website login shares credentials set up through the bot (Argon2-hashed passwords, JWT sessions)
- Dashboard: income/expense/balance totals, category breakdown (donut chart), monthly *and* daily trend views, recent transactions
- Custom date-range filtering across the whole dashboard
- CSV report exports (transactions and summary), respecting the active date filter
- Structured error handling and logging on both the bot and API side
- Bot and web app run together as one always-on service, no separate process to babysit

## Tech stack

Python · python-telegram-bot · FastAPI · PostgreSQL (Supabase) · psycopg2 · JWT (python-jose) · Argon2 (passlib) · Chart.js · vanilla JS/HTML/CSS · Render (deployment)

## Setup

### 1. Database
Create a Supabase project (or any PostgreSQL instance). Run the schema/migration SQL in `webapp/migration.sql` to set up the `Users`, `Expenses`, and `Income` tables. Use the **connection pooler** string (Supavisor, port 6543) rather than the direct connection string — this avoids IPv6-only connectivity issues on hosts like Render that don't support outbound IPv6.

### 2. Bot + Website (single service)
```bash
cd webapp
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL, JWT_SECRET_KEY, TELEGRAM_BOT_TOKEN
uvicorn main:app --reload
```
Visit `http://localhost:8000`. The bot starts automatically alongside the web server via a FastAPI startup hook — no separate process needed.

### 3. Deploying (Render)
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT` (run from the `webapp` root directory)
- **Environment variables:** `DATABASE_URL` (Supabase pooler string), `JWT_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`

## What I learned building this

- **Local dev and production are different problems.** The database originally used local/Windows-style auth, which only worked because everything ran on one PC — deploying anywhere else meant rethinking auth and connectivity from scratch.
- **Schema decisions echo through every layer.** Splitting "display name" from "unique login ID" after the fact touched the bot's signup flow, the database queries, and the API auth layer simultaneously.
- **Secrets management isn't optional.** Moved from hardcoded credentials to environment variables (`.env`, gitignored) before this became public — a good habit to build early rather than retrofit.
- **Networking details matter in production.** Hit an IPv6-vs-IPv4 mismatch between Render and Supabase's direct connection string — cloud platforms and managed databases don't always speak the same protocol by default, and the fix (a connection pooler) isn't obvious until you hit the error.
- **Background processes need a host too.** A Telegram bot polling for messages doesn't stop just because your laptop does. Running it as an async task inside the same web service (instead of a separate always-on process) kept the whole project on a single free-tier deployment.

## Roadmap

- [x] Move off local SQL Server to a cloud-hosted database (PostgreSQL via Supabase)
- [x] Deploy bot + website to run 24/7 independent of any single machine (Render)
- [ ] Containerize (Docker) for consistent deployment
- [ ] `/resetpassword` command for the bot

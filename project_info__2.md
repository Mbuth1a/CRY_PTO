# FraudLab Simulator — Codebase Overview

## Summary
FraudLab Simulator is a Django 5.2 web application that simulates a synthetic cryptocurrency/trading platform for defensive security research and reverse-engineering exercises. It deliberately mimics M-Pesa deposits, Binance deposits, USDT/KES wallets, BTCUSDT market ticks, and trading positions — but **never connects to any real payment network, exchange, or blockchain**. It ships with a dark-themed dashboard, JSON APIs, an audit-event trail, and a Django admin interface. All values are synthetic by design.

## Architecture

### Primary Architectural Pattern
Classic **layered Django monolith**:
- **Template layer**: server-rendered Django templates (`templates/`) with an ES5-era vanilla-JS frontend (`static/app.js`) that calls JSON endpoints via `fetch`.
- **View layer**: function-based views in `simulator/views.py` — HTML pages for auth/dashboard + JSON APIs for market, deposits, withdrawals, conversions, positions, and audit events.
- **Service layer**: `simulator/services.py` holds all business logic (deposits, withdrawals, conversions, market ticks, audit) — views are thin wrappers around services. This is the closest thing the codebase has to a domain layer.
- **Model layer**: 7 Django models in `simulator/models.py` mapping directly to SQLite tables.

### Technology Stack
- **Backend**: Python + Django 5.2.17 (`Django>=5.2,<5.3` — the only runtime dependency in `requirements.txt`)
- **Database**: SQLite (`db.sqlite3`) — `django.db.backends.sqlite3`
- **Frontend**: Server-rendered templates + vanilla JavaScript on an HTML `<canvas>` chart; no build step, no framework
- **Auth**: Django's default `User` model + session auth (`django.contrib.auth`)
- **Time zone**: `Africa/Nairobi`, UTC+3

### Execution Flow
1. Entry point is `manage.py` → reads `DJANGO_SETTINGS_MODULE=fraudlab.settings` → calls `django.core.management.execute_from_command_line`.
2. `fraudlab/urls.py` mounts `django.contrib.admin` at `/admin/` and everything else under `simulator.urls`.
3. `simulator/urls.py` defines 9 routes: `home`, `login`, `logout`, `dashboard`, and 6 JSON API endpoints (`api/market/`, `api/deposit/`, `api/withdraw/`, `api/convert/`, `api/position/`, `api/events/`).
4. `simulator/management/commands/seed_demo.py` is a management command (`python manage.py seed_demo`) that creates the demo user `labuser` / `LabOnly-ChangeMe-123!`, two wallets (USDT 25,000 / KES 100,000), an initial BTCUSDT tick at 65,000, and writes a `DEMO_SEED` audit event.

## Directory Structure

```
fraudlab_simulator/
├── manage.py                  — Django CLI entry point
├── requirements.txt           — Django>=5.2,<5.3 (only dependency)
├── README.md                  — Safety boundary docs + reverse-engineering exercises
├── db.sqlite3                 — Local SQLite database (dev artifact)
├── fraudlab.log               — Log file written by the fraudlab logger
├── .venv/                     — Virtualenv (Django installed 8/14/2026; see Non-Obvious #1)
├── fraudlab/                  — Project package
│   ├── settings.py            — All Django settings (DEBUG=True, SQLite, LOGGING)
│   ├── urls.py                — admin/ + include(simulator.urls)
│   └── wsgi.py                — WSGI entry point
├── simulator/                 — The single Django app (all business logic)
│   ├── models.py              — 7 models (see Key Abstractions)
│   ├── views.py               — 9 function-based views (HTML + JSON)
│   ├── services.py            — Business logic: deposits, withdrawals, conversions, ticks, audit
│   ├── urls.py                — Route table
│   ├── admin.py               — Registers all models with the admin
│   ├── apps.py                — AppConfig
│   ├── management/commands/seed_demo.py — Seeds demo user/wallets/tick
│   └── migrations/            — 0001_initial, 0002_syntheticconversion
├── static/
│   ├── app.css                — Dark theme (single stylesheet)
│   └── app.js                 — fetch-based JS: market refresh, deposits, withdrawals, positions, conversion, chart canvas
└── templates/
    ├── dashboard.html         — Main dashboard (wallets, market, controls, audit feed, payments table)
    └── login.html             — Login page (pre-filled demo credentials)
```

## Key Abstractions

### User (Django built-in, `django.contrib.auth.models.User`)
- **File**: Django framework
- **Responsibility**: Authentication identity. Every model in the app has a FK to it. `seed_demo` creates `labuser`.
- **Used by**: `DemoProfile`, `DemoWallet`, `Position`, `SyntheticPayment`, `SyntheticConversion`, `AuditEvent`.

### DemoWallet (`simulator/models.py`)
- **File**: `simulator/models.py` (~line 18)
- **Responsibility**: A user's synthetic asset balance. One row per (user, asset). Balance is `DecimalField(max_digits=24, decimal_places=8)`.
- **Interface**: `user` FK, `asset` (default `"USDT"`), `balance` (default 0), `address` (unique, e.g. `demo_usdt_wallet_001`).
- **Lifecycle**: Created lazily by `get_or_create` in `synthetic_deposit()` and `synthetic_convert_kes_to_usdt()` when a deposit/conversion targets an asset the user doesn't have yet.
- **Key invariant**: No DB-level constraint preventing negative balance — the only guard is `synthetic_withdrawal()` checking `wallet.balance < amount` before deducting. Race conditions could produce negative balances.

### SyntheticPayment (`simulator/models.py`, ~line 68)
- **File**: `simulator/models.py`
- **Responsibility**: Ledger record for every synthetic deposit/withdrawal. Direction is `DEPOSIT` or `WITHDRAWAL`; provider is `MPESA` or `BINANCE`; status defaults to `COMPLETED` (PENDING/BLOCKED choices exist but are never set by code).
- **Interface**: `user`, `provider`, `direction`, `amount`, `asset`, `reference` (unique, e.g. `SIM-...` or `SIM-WD-...`), `metadata` JSON, `created_at`.
- **Lifecycle**: Created inside `@transaction.atomic` service functions; every deposit credits and every withdrawal debits the matching `DemoWallet`.
- **Known gap**: `deposit_api`/`withdrawal_api` in views never set/return a `status`, and services hard-code `COMPLETED`.

### MarketTick (`simulator/models.py`)
- **File**: `simulator/models.py`
- **Responsibility**: Append-only price snapshots for the synthetic BTCUSDT market. Price is `DecimalField(max_digits=24, decimal_places=8)`.
- **Interface**: `symbol`, `price`, `created_at`; `Meta.ordering = ["-created_at"]`.
- **Lifecycle**: Created by `generate_market_tick()`; seeded at 65,000 by `seed_demo`. `Position.unrealized_pnl` reads the most recent tick to compute P&L.

### Position (`simulator/models.py`, ~line 46)
- **File**: `simulator/models.py`
- **Responsibility**: A user's open synthetic long/short on BTCUSDT.
- **Interface**: `user`, `symbol`, `side` (`LONG`/`SHORT`), `quantity`, `entry_price`, `opened_at`, `closed_at` (nullable), `status` (default `"OPEN"`), plus `unrealized_pnl` property that computes latest-tick delta × quantity (flipped for SHORT).
- **Lifecycle**: Created by `open_position()` in services. **Nothing in the codebase ever closes a position** — `closed_at`/`status` never get set to non-default values. There is no margin/balance check before opening a position.

### SyntheticConversion (`simulator/models.py`, ~line 86)
- **File**: `simulator/models.py`
- **Responsibility**: Records a KES→USDT conversion done at the fixed synthetic rate (default 130).
- **Interface**: `user`, `from_asset`/`to_asset` (KES or USDT), `from_amount`, `to_amount`, `rate`, `reference` (unique, `SIM-FX-...`), `created_at`.
- **Lifecycle**: Created inside `transaction.atomic` block in `synthetic_convert_kes_to_usdt()`; debits KES wallet, credits USDT wallet, then writes the record and audit event atomically.

### AuditEvent (`simulator/models.py`, ~line 100)
- **File**: `simulator/models.py`
- **Responsibility**: Append-only audit trail of everything significant (logins, deposits, withdrawals, conversions, position opens, seed).
- **Interface**: `user` (nullable, `SET_NULL`), `event_type`, `severity` (`INFO`/`WARN`/`HIGH`), `message`, `ip_address` (nullable), `metadata` JSON, `created_at`.
- **Note**: `fraudlab/settings.py` LOGGING has a `fraudlab` logger (console + file) and `audit()` in services logs each event — so audit events go to both the DB and `fraudlab.log` (the logger name matches: `logging.getLogger("fraudlab")`).

### Service layer functions (`simulator/services.py`)
- `audit(event_type, message, user, severity, metadata, ip_address)` — creates AuditEvent + logs to `fraudlab` logger.
- `generate_market_tick()` — random walk ±1.2% of last tick, quantized to 8 decimals.
- `synthetic_deposit(user, provider, amount, asset)` — `@transaction.atomic`; validates amount, creates SyntheticPayment (COMPLETED), credits wallet, audits.
- `synthetic_withdrawal(user, provider, amount, asset)` — `@transaction.atomic`; validates balance, debits wallet, creates payment, audits.
- `open_position(user, quantity, side)` — creates Position at latest tick (generating one if none), audits. No balance check.
- `synthetic_convert_kes_to_usdt(user, kes_amount, rate=130)` — `@transaction.atomic`; validates KES balance, debits KES, credits USDT at amount/rate, writes SyntheticConversion + audit.

## Data Flow

### Login flow
1. `templates/login.html` POSTs `username` + `password` to `/login/`.
2. `views.login_view` calls `authenticate()` — on failure writes a `LOGIN_FAILURE` WARN audit and re-renders login with error; on success calls `login()`, writes `LOGIN_SUCCESS` audit, redirects to `dashboard`.

### Market refresh flow (the primary "runtime loop")
1. `static/app.js` on `window.load` calls `refreshMarket()` → GET `/api/market/`.
2. `views.market_api` calls `generate_market_tick()` → **writes a new MarketTick row on every request** (the endpoint has a side effect; it's not read-only despite `@require_GET`).
3. It also queries the last 30 ticks (reversed to chronological) and returns `{price, history[]}` as JSON.
4. `app.js` updates `#price` text and `drawChart()` paints a canvas line chart.

### Deposit flow
1. Dashboard `deposit(provider)` → POST `/api/deposit/` with `{provider, amount}` + CSRF token.
2. `views.deposit_api` derives asset from provider (`MPESA`→KES, otherwise USDT), calls `synthetic_deposit()`.
3. Service validates amount > 0, creates SyntheticPayment with reference `SIM-...`, `get_or_create`s a wallet for (user, asset), credits balance, audits.
4. Response JSON includes `synthetic: true`, reference, provider, amount, asset. Frontend `alert()`s the JSON then `location.reload()`.

**Important user-reported bug (confirmed in code)**: A synthetic M-Pesa deposit credits a **KES** wallet, not a USDT wallet. The dashboard's "USDT Wallet" card only reads `DemoWallet(user, asset="USDT")`, so an M-Pesa deposit (KES) visibly does nothing to the displayed USDT balance — exactly what the user complained about: "the synthetic M-pesa deposit should populate the USDT wallet." The M-Pesa amount lands in a KES wallet that the dashboard never displays.

### Withdrawal flow
1. `withdraw(provider)` → POST `/api/withdraw/` → `views.withdrawal_api` → `synthetic_withdrawal()`.
2. Service checks wallet balance ≥ amount, debits, creates payment with `SIM-WD-...` reference, audits. Errors (non-positive amount, insufficient balance) return HTTP 400 with `{error}`.

### KES→USDT conversion flow
1. `convertKes()` → POST `/api/convert/` with `amount` → `views.convert_api` → `synthetic_convert_kes_to_usdt(user, amount)`.
2. Service uses fixed rate 130, debits KES wallet, credits USDT wallet, writes `SyntheticConversion` + `SYNTHETIC_CONVERSION` audit, returns conversion JSON.

### Position flow
1. `openPosition()` → POST `/api/position/` → `views.position_api` → `open_position()`.
2. Service creates Position at latest tick price (generates a tick if the table is empty), audits `POSITION_OPENED`. Returns id/side/quantity/entry_price.

### Audit events flow
1. `refreshEvents()` on load and after each market refresh GETs `/api/events/`.
2. `views.events_api` returns the user's 50 most recent AuditEvent rows as JSON (type, severity, message, time).
3. `app.js` renders them as `div.event` blocks. The dashboard template itself does NOT render AuditEvents server-side (only via JS).

## Non-Obvious Behaviors & Design Decisions

1. **The venv was empty until 8/14/2026** — Django was not installed when the project was created; only pip/setuptools existed. The Pylance "django.db could not be resolved" warning was an environment problem. `pip install -r requirements.txt` into `.venv` fixed it. Anyone opening this repo must install requirements into their interpreter or Pylance/Python both fail.
2. **`/api/market/` mutates state.** Despite being `@require_GET`, it calls `generate_market_tick()` which inserts a MarketTick row on every hit. Every dashboard page load and every "Generate synthetic tick" click grows the table. There is no interval-based market loop — ticking is demand-driven.
3. **M-Pesa deposits credit KES, not USDT.** This is the documented behavior in code but contradicts the dashboard's focus on the USDT wallet — the user-facing bug. The KES wallet is invisible in the UI (it only matters as a backing balance for conversions). Fixing "M-Pesa deposit populates USDT wallet" means changing `deposit_api`/`synthetic_deposit` semantics (e.g., M-Pesa converts to USDT on credit, or the dashboard should show the KES wallet too).
4. **No position closing anywhere.** `Position.status`/`closed_at` support a lifecycle, and `unrealized_pnl` exists, but no code closes positions, realizes P&L, or adjusts wallets on close. Positions are one-way.
5. **No balance/margin validation for positions.** `open_position()` never checks wallet balance against quantity×entry_price. A user can open arbitrarily large positions with 0 USDT.
6. **The dashboard's cards render server-side, but after any JS action the page does a `location.reload()`** — so server-side state and client state stay in sync only via full reloads, not via the API responses. The API returns JSON that is `alert()`ed (a debug artifact) then discarded.
7. **`AuditEvent` is dual-write**: DB row + `fraudlab.log` file via the `fraudlab` logger. The audit trail is the project's core research value (README exercises #4/#6/#7/#8 all lean on it).
8. **Status choices are vestigial.** `SyntheticPayment.STATUSES` includes PENDING/BLOCKED and `Position.status` supports OPEN/CLOSED concepts, but the code writes only `COMPLETED`/`OPEN`. The enums suggest intended future flows (fraud-blocking, pending clearing) that don't exist.
9. **Security posture is intentionally non-production**: `SECRET_KEY` hard-coded, `DEBUG=True`, `ALLOWED_HOSTS=["127.0.0.1","localhost"]`, `AUTH_PASSWORD_VALIDATORS=[]`, demo password in the login form's `value` attribute, no rate limiting, all API endpoints are session+`login_required` but there are no permissions tiers. CSRF is handled properly (tokens sent), but no input length/format validation beyond Decimal parsing.
10. **Decimal precision discipline is mostly consistent**: every money field is `max_digits=24, decimal_places=8`; conversions quantize to 8 decimals. One inconsistency: `open_position` is NOT `@transaction.atomic` while deposits/withdrawals/conversions are, and `Position.quantity` is accepted as-is without a > 0 check.
11. **`from .models import SyntheticConversion` inside `services.py` function body** — a local import to avoid a circular import; the module-level import list omits it.
12. **No `asgi.py`, no static collection config for production, no environment-based settings split, no requirements split, no tests directory, no `whitenoise`** — all standard production-readiness gaps.
13. **`fraudlab/urls.py` has no static/media URL routing** for `DEBUG=False`; `STATIC_URL = "static/"` with `STATICFILES_DIRS` works in dev via Django's staticfiles app only.

## Production-Readiness Gap Analysis (what "upgrade to production level" would entail)

### Critical / security
- Move `SECRET_KEY` to environment variable; gate `DEBUG` on env (e.g. `settings_production.py` or `django-environ`).
- Set `ALLOWED_HOSTS` from env; add security middleware headers (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy) — some Django security middleware is present but its settings are defaulted off.
- Replace hard-coded demo password; add real `AUTH_PASSWORD_VALIDATORS`; remove password from login form `value` attribute.
- Rate-limit login and API endpoints (`django-ratelimit` or middleware).
- Validate limits: max amount, max position size, allowed provider/asset combos; enforce wallet balance on `open_position`.
- Stop `alert()`-ing JSON responses (UX/info leak) — render inline feedback instead.
- Add Content-Security-Policy (`django-csp`).

### Data integrity
- Add a migration for `CheckConstraint` on `DemoWallet.balance >= 0` (or enforce with `select_for_update()` in withdrawal/conversion to close the race).
- Decide M-Pesa semantics: either show the KES wallet in the dashboard (so deposits are visible) or change deposit logic so M-Pesa converts to USDT (the user's requested behavior).
- Implement position closing (realized P&L, wallet settlement) or remove the dead `status`/`closed_at` fields.

### Operations
- Harden logging: rotate files (`RotatingFileHandler`), avoid logging sensitive data, add request logging.
- Switch to PostgreSQL (`dj-database-url` env-driven) or keep SQLite only for dev.
- Add `asgi.py`, gunicorn/uvicorn config, Procfile/Dockerfile, `collectstatic` with `whitenoise` or CDN.
- Add a test suite (pytest-django or Django TestCase) — currently **zero tests exist**.
- Add `django-environ`/`.env` conventions, `requirements-prod.txt`, CI config, ruff/black/mypy tooling.
- Add migrations for model changes; review `blank=True` on form-facing fields.

### Maintainability
- Split `views.py` into dashboard vs API (or use Django REST Framework); the function-based JSON views are hand-rolled.
- Extract constants (rate 130, symbol `BTCUSDT`, asset defaults) into `simulator/constants.py`.
- Add a `MarketTick` purge/retention policy or cap history (the table grows unbounded on every `/api/market/` hit — in production this is a storage DoS vector for logged-in users).
- Add a base template (`{% extends %}`) — the two templates duplicate the stylesheet link.
- Register `SyntheticConversion` in admin (currently missing).

## Module Reference

| File | Purpose |
|------|---------|
| `manage.py` | Django CLI entry point |
| `fraudlab/settings.py` | All project config (dev-grade: DEBUG, SQLite, hard-coded SECRET_KEY) |
| `fraudlab/urls.py` | URL root: mounts admin + simulator app |
| `fraudlab/wsgi.py` | WSGI application object |
| `simulator/models.py` | 7 models: DemoProfile, DemoWallet, MarketTick, Position, SyntheticPayment, SyntheticConversion, AuditEvent |
| `simulator/views.py` | 9 function-based views: home, login_view, logout_view, dashboard, market_api, deposit_api, withdrawal_api, convert_api, position_api, events_api |
| `simulator/services.py` | Business logic: audit, generate_market_tick, synthetic_deposit, synthetic_withdrawal, open_position, synthetic_convert_kes_to_usdt |
| `simulator/urls.py` | Route table for the simulator app |
| `simulator/admin.py` | Registers all 6 models (SyntheticConversion missing) with Django admin |
| `simulator/apps.py` | AppConfig for `simulator` |
| `simulator/management/commands/seed_demo.py` | Seeds labuser, wallets (USDT 25k / KES 100k), initial BTCUSDT tick, DEMO_SEED audit |
| `simulator/migrations/0001_initial.py` | Initial schema (all models except SyntheticConversion) |
| `simulator/migrations/0002_syntheticconversion.py` | Adds SyntheticConversion model |
| `static/app.js` | Vanilla-JS: CSRF helper, market refresh, canvas chart, deposit/withdraw/position/conversion POSTs, audit feed rendering |
| `static/app.css` | Dark theme: layout cards, badges, forms, tables, event feed |
| `templates/dashboard.html` | Main dashboard (server-rendered wallets/market + JS-driven audit feed) |
| `templates/login.html` | Login page with pre-filled demo credentials |
| `README.md` | Safety boundary + 10 reverse-engineering exercise prompts |
| `requirements.txt` | `Django>=5.2,<5.3` (only runtime dep) |

## Suggested Reading Order

1. `README.md` — understand the safety boundary and what the project is *for* (defensive research lab, not a real exchange). This reframes every "production" decision.
2. `simulator/models.py` — the data model is the backbone; everything else (views, services, templates) is a thin layer over it.
3. `simulator/services.py` — all business logic lives here; this is where the M-Pesa→KES semantics and fixed 130 conversion rate live.
4. `simulator/views.py` — see how thin the view layer is, how `@require_GET`/`@require_POST` + `@login_required` are applied, and how errors map to HTTP 400.
5. `static/app.js` + `templates/dashboard.html` — the frontend contract: endpoints, expected request params, response shape, and the `alert()+reload()` pattern.
6. `fraudlab/settings.py` — the dev-grade settings that must change first for any production deployment.

## Key Production Upgrade Recommendations (prioritized)

1. **Config**: env-driven `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, database URL; split settings into `base/prod/dev`.
2. **Security middleware**: enable HSTS/CSP/X-Frame-Options, password validators, remove hard-coded credentials, rate-limit login/APIs.
3. **Fix the M-Pesa → USDT wallet behavior** (user-reported) — decide and implement the intended mapping; add a KES wallet display or auto-convert to USDT.
4. **Data integrity**: add `CheckConstraint(balance >= 0)` + `select_for_update()` in withdrawal/conversion; validate position quantity and wallet balance before `open_position`.
5. **Market ticker DoS**: cap `/api/market/` history growth (retention job), or make history read-only and tick only via a scheduled task/cron.
6. **Tests**: add pytest/Django TestCase coverage for services (deposit, withdrawal, conversion, position) — currently zero.
7. **Deployment**: `asgi.py` or gunicorn + whitenoise for static; PostgreSQL for prod; Dockerfile + CI; log rotation.
8. **Code quality**: constants module, split views, register SyntheticConversion in admin, remove vestigial status choices or implement close-position flow.

---

**Note on the user's request**: The request "check the codebase and upgrade it to production level site" requires writing code (settings changes, new migration, tests, etc.), which Explore Mode cannot perform. To implement the production upgrade, switch to **Act Mode** using the mode selector at the bottom of the chat — all findings above (especially the prioritized upgrade list and the confirmed M-Pesa→KES→USDT bug) will carry over as context.
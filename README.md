# RPG Horizon Radar

M&A and competitive-intelligence signal-surfacing agent for RPG Corporate Strategy — continuously scans
public signals (news, filings, patents, hiring patterns), scores distress/opportunity, and routes a
small number of genuinely notable items to the strategy teams who sign in. It is a
**flagging tool, not a valuation or decisioning tool**: once a signal is worth pursuing, it hands off
to RPG's existing formal, restricted M&A process and exits this system's scope entirely.

**Read [DESIGN.md](DESIGN.md) first** — it's the authoritative HLD: problem statement, access model
(§4: every signed-in user sees everything; no roles, gates or approvals), data model, the CEAT pilot
cascade example, and the acquisition thesis (§14).

Generated from the **accelerator-bootstrapper-template** (ZenLabs Agent Foundry) — same stack and
conventions as `digital-onboarding`, `zenarc`, `merchant-onboard`, `capmarkets`.

## Architecture

FastAPI (async) + PostgreSQL (SQLAlchemy async + Alembic) + Redis + Temporal (durable workflows) +
OpenTelemetry/Arize Phoenix, React/Vite/Tailwind (TypeScript) UI served by nginx. Deploys to Azure
Container Apps. See [DESIGN.md §10](DESIGN.md#10-implementation-architecture-this-build) for exactly
how Horizon Radar uses (and deliberately doesn't use) each piece of this stack — short version: scoring
is rule-based by design (never an LLM call), and the one piece of platform infra this app's own
pipeline genuinely relies on is **Temporal**, for durable, retryable signal ingestion.

## Run locally

```bash
cd app
cp .env.example .env                                  # then set FIRST_USER_EMAIL and FIRST_USER_PASSWORD
docker compose -f ../docker-compose.local.yml up -d    # postgres + redis
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
alembic upgrade head
uvicorn api.main:app --reload --port 8040              # API — creates the six subsidiaries and the first user

cd ui && npm install && npm run dev                    # UI on :5173
```

The app ships no demo data and no default logins. On a start against a database where nobody can sign
in, it creates the six RPG subsidiaries and one user from `FIRST_USER_EMAIL` / `FIRST_USER_PASSWORD`
(`FIRST_USER_PASSWORD_KV_URI` when deployed). Users have no roles: everyone sees every RPG company and
can change everything. Sign in, then:

1. **Users and watchlist → Users:** add your colleagues.
2. **Radar settings → Watched companies → Find rivals now** (needs `TAVILY_API_KEY` and an LLM key),
   or add companies by hand in **Users and watchlist → Watchlist**. Found companies are watched at once.
3. **Refresh live signals** (same screen), or wait for the daily run.

Until then the screens are empty and say what would fill them.

An existing database from an earlier version: `alembic upgrade head` runs migration
`0004_remove_demo_data` (removes the old fictional companies and demo logins) and
`0005_remove_approvals` (drops roles, sector gates and watchlist approval; proposed companies become
watched). See DESIGN.md §15.

For durable ingestion via Temporal (optional — `POST /api/v1/ingest/run` falls back to an inline call
if this isn't running):
```bash
cd app && docker compose up --build     # full stack: API, worker, Temporal, Phoenix
```

Without Docker, use SQLite: set `DATABASE_URL=sqlite+aiosqlite:///./horizon_radar.db` in `app/.env`,
then `alembic upgrade head` and start the API as above. Redis and Temporal are optional for the
Horizon Radar pipeline.

## Live signals on real companies

See [DESIGN.md §15](DESIGN.md#15-addendum--live-signals-on-real-companies). In short:

- Add API keys to `app/.env` (listed in `.env.example`); each connector runs only when its key is set.
- **Users and watchlist → Watchlist:** discovery finds competitors and adjacent players for every
  subsidiary, with its sources, and they are watched at once. Anyone can remove a company (discovery
  never re-adds it) or add one by hand.
- **Users and watchlist → Live Sources:** which connectors are configured, their pace and daily budgets, the
  schedule (daily ingestion at 17:00, weekly discovery) and the last run's errors.
- **This week:** the watched companies with their public signals and rule-based scores.
  Each RPG company's SWOT is written by the SWOT Analyst from public facts about the company itself
  (quarterly results, shareholding, web and news; `services/company_research.py`) and its watched
  companies' signals, every item citing its sources, rebuilt weekly (**Build SWOT** runs it now). What it
  reads and judges each company on are checkboxes in **Radar settings → SWOT parameters**.
- **Today's opportunities and threats** (This week): every morning the Opportunity Analyst reads the
  news about each company, its watched companies and its industry, and reports what it means for the
  SWOT. Keep a finding to feed it into the next weekly SWOT.
- Tests: `cd app && pytest` (no network; connectors and the model are faked).

## The app's screens

The UI is the Horizon Radar radar design (see [DESIGN.md §16](DESIGN.md#16-addendum--the-radar-screens-the-apps-main-ui)):
Radar (M&A Signals with each signal's acquisition thesis, Competitor Analysis, Ask Radar, Shortlisted
signals, Radar settings), Self reflection (Self analysis, Weekly digest, The financial market) and
Workspace (Digest archive, Users and watchlist). Every screen needs a login and is recorded in the
activity history (Users and watchlist → Activity).

## Deploy to Azure Container Apps
```bash
bash infra/aca-setup.sh          # one-time provisioning (edit VARIABLES first)
```
Or push to `main` and let `azure-pipelines-be.yml` / `azure-pipelines-fe.yml` deploy. Every user of a
deployment sees all of its data, so control who gets an account, and run it in a restricted network
segment rather than on shared or public infrastructure.

## Layout

See [DESIGN.md §10](DESIGN.md#10-implementation-architecture-this-build) for the full annotated
directory map (what's Horizon Radar's own code vs. the accelerator's baseline scaffold kept as-is).

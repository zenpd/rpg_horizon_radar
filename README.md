# RPG Horizon Radar

M&A and competitive-intelligence signal-surfacing agent for RPG Corporate Strategy — continuously scans
public signals (news, filings, patents, hiring patterns), scores distress/opportunity, and routes a
small number of genuinely notable items to a **named, restricted reviewer list**. It is a
**flagging tool, not a valuation or decisioning tool**: once a signal is worth pursuing, it hands off
to RPG's existing formal, restricted M&A process and exits this system's scope entirely.

**Read [DESIGN.md](DESIGN.md) first** — it's the authoritative HLD: problem statement, governance
model (UPSI/SEBI framing, named-reviewer allow-list, sector gating), data model, the CEAT pilot
cascade example, and the Escalation Brief hand-off packet (§14).

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
cp .env.example .env                                  # dev defaults work as-is; no API keys required
docker compose -f ../docker-compose.local.yml up -d    # postgres + redis
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
alembic upgrade head
uvicorn api.main:app --reload --port 8040              # API — seeds demo data on first boot

cd ui && npm install && npm run dev                    # UI on :5173
```

Demo reviewer logins (printed to the API's console on first seed, local prototype only):

| Email | Password | Role |
|---|---|---|
| `compliance.admin@rpg-demo.local` | `ChangeMe123!` | `compliance_admin` |
| `strategy.ceat@rpg-demo.local` | `ChangeMe123!` | `corp_strategy_reviewer` (CEAT scope) |
| `strategy.kec@rpg-demo.local` | `ChangeMe123!` | `corp_strategy_reviewer` (KEC scope) |

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
- **Admin → Watchlist:** discovery proposes competitors and adjacent players for gate-open
  subsidiaries, with its sources. Nothing about a company is fetched until a `compliance_admin`
  approves it. Companies can also be added by hand.
- **Admin → Live Sources:** which connectors are configured, their pace and daily budgets, the
  schedule (daily ingestion at 17:00, weekly discovery) and the last run's errors.
- **SWOT Briefs:** a cited SWOT per subsidiary, rebuilt after each run that brings new signals. Add the
  strategy team's strengths and weaknesses there; the brief takes those only from the team's notes.
- Tests: `cd app && pytest` (no network; connectors and the model are faked).

## Deploy to Azure Container Apps
```bash
bash infra/aca-setup.sh          # one-time provisioning (edit VARIABLES first)
```
Or push to `main` and let `azure-pipelines-be.yml` / `azure-pipelines-fe.yml` deploy. **Before any real
pilot deployment:** DESIGN.md §4 requires Company Secretary / Compliance sign-off on the access model
and reviewer list as a precondition, and the app must run in a restricted network segment, not
shared/public infrastructure — the pipeline/ACA setup gives you the mechanics, not that sign-off.

## Layout

See [DESIGN.md §10](DESIGN.md#10-implementation-architecture-this-build) for the full annotated
directory map (what's Horizon Radar's own code vs. the accelerator's baseline scaffold kept as-is).

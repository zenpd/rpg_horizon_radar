# Horizon Radar — remaining work

Status as of 7 Oct 2026, branch `remove-demo-data`. The app holds no demo data: every screen shows
watched companies' public signals, rule-based scores and what users did, or an empty state that says
what would fill it. There are no roles, sector gates or approvals: every signed-in user sees and can
change everything (DESIGN.md §4). See DESIGN.md §15–16.

## 0. Next up (requested 8 Oct 2026)

- [ ] **A common landing page, and every other tab specific to the selected company.**
  - The landing page is the same for all users and all subsidiaries: M&A-related news across every
    opportunity, whichever RPG company it belongs to (new M&A signals, Sector Scout finds, deals,
    stake sales, distress and fund-raise news), each item tagged with the RPG company it is for.
  - Every other tab (M&A Signals, Competitor Analysis, Ask Radar, Shortlisted signals, Radar settings,
    Self analysis, Weekly digest, The financial market) shows only the subsidiary picked in the
    company box. Today some tabs accept "All companies"; decide whether "All" stays as a choice
    outside the landing page.
- [ ] **Rename "Connections" in the acquisition thesis.** The word reads like social connections. The
  section lists shareholders, the promoter group, parent, subsidiaries, joint ventures, partners, key
  customers and suppliers, and directors. Candidate names: "Ownership and business ties",
  "Corporate relationships" or "Group structure and partners". Rename the thesis tab, the section
  heading, the graph's label and the agent's wording together.

## 1. Before anyone outside the build team uses it

- [ ] **Licence and terms checks.**
  - [ ] NSE's terms on automated access to its site API. The connector can be switched off with
    `NSE_ENABLED=false`.
  - [ ] Glassdoor via Fetchlayer, which scrapes Glassdoor. This connector is not built until it is
    cleared.
- [ ] **Rotate every API key** that was pasted into chat during the build: NVIDIA, Groq, Azure
  OpenAI, Tavily, GNews, YouTube, EPO, Alpha Vantage, Fincrux and Fetchlayer. In deployed
  environments, move them to Key Vault (`*_kv_uri` settings).
- [ ] **First user per environment.** Set `FIRST_USER_EMAIL` and `FIRST_USER_PASSWORD_KV_URI` before
  the first start (renamed from `ADMIN_*`); that user adds the others. Every user sees all data, so
  decide who gets an account.
- [ ] **Run migrations `0004_remove_demo_data` and `0005_remove_approvals`** on every existing database
  (`alembic upgrade head`). Both tested on SQLite (upgrade, downgrade, re-upgrade); not yet run on
  PostgreSQL. 0005 turns every proposed company into a watched one.

## 2. Real sources still to build

| Screen | Today | To do |
|---|---|---|
| SWOT (This week) | Built weekly for all six from public research on each company, following each company's SWOT parameters; a daily Opportunity Analyst judges the news against it | Fincrux's 5 calls a day cover only about five companies, so results arrive over two days; Raychem RPG (unlisted) has only web and news facts. Next: the same research for acquisition targets and a target-versus-subsidiary comparison |
| Acquisition theses | Criteria are saved; no matches | Source acquisition targets (sector, revenue, ownership), then match theses against them |
| Market performance | Empty state | Alpha Vantage daily prices for the watched companies (25 calls a day) |
| Watch rules | Opportunity score only | Add metrics as data arrives (promoter pledge %, credit rating) |
| Book pages | Signals, score and a standard plan | A research step per escalated company (filings, results) |
| NewsData.io, Adzuna | Built but off (no keys) | Add `NEWSDATA_API_KEY`, `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` |
| Azure gpt-4.1-mini | HTTP 403 (public network access disabled), so thesis parsing and Ask Radar fall back to rules | Private endpoint or allowed network for the API's host |

## 3. Persistence and platform

- [x] **No roles, gates or approvals** (migration 0005): discovery's companies are watched at once,
  anyone can remove one, and the audit log is the activity history every user can read.
- [x] **Radar state in the database.** What users do (case stage, owner, plan, outcome), the book
  order, theses, watch rules, universe and activity are snapshotted into `connector_state` after
  every change and restored at boot (`radar/persistence.py`).
- [x] **Background work across replicas.** Only the replica holding the `scheduler` lease
  (`services/lease.py`) runs scheduled ingestion and discovery; another takes over within 3 minutes
  if it stops. Job records are stored, so any replica answers a poll, and only one job per kind runs
  across replicas.
- [x] **Deployment settings**, **quiet tracing locally**, **CI** (see git history).
- [x] **Migrations 0003, 0004 and 0005.** 0003 tested on PostgreSQL; 0004 and 0005 on SQLite only (above).

## 4. Code and tests

- [x] **LLM agents in one place.** `app/agents/` holds the SWOT Analyst, watchlist discovery and their
  model clients; the template's unused LangGraph example is removed.
- [x] **Prototype tests ported:** LLM route behaviour (`tests/test_llm_routes.py`), Azure thesis
  parsing and Ask Radar fallbacks (`tests/test_radar.py`).
- [ ] **Review the Escalation Brief wording** now that it names real companies (DESIGN.md §14).
- [ ] **Dark theme for the desk screens.** The Restricted desk screens (Signal board, Digests, Users and watchlist)
  stay light in dark theme; theme them if needed.
- [ ] **One place to manage the watchlist.** Users and watchlist → Watchlist and Radar settings →
  Watched companies both show watchlist information, and the radar's "universe" list overlaps with it.
  Decide which screen owns it.
- [ ] **Unused radar CSS.** Styles for the removed demo charts, deep-dive timer and guided tour are
  still in `app/ui/src/radar/styles.css`.
- [ ] **Archive the old prototype folder** (`Claude outputs/RPG_Horizon_Radar`) once the team is on
  this repo. Its live caches and `.env` are local only.

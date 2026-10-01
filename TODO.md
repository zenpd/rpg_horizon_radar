# Horizon Radar — remaining work

Status as of 1 Oct 2026, branch `dev_sow`. The radar screens run on this repo's backend. Live
signals flow only for **approved** watchlist companies in sectors whose **compliance gate is open**.
Everything else on the screens is still the prototype's demo data. See DESIGN.md §15–16.

## 1. Before anyone outside the build team uses it

- [ ] **Compliance sign-off.** Company Secretary / Compliance approve watching real, listed
  companies (DESIGN.md §4). Record the reference in DESIGN.md §15.
- [ ] **Licence and terms checks.**
  - [ ] NSE's terms on automated access to its site API. The connector can be switched off with
    `NSE_ENABLED=false`.
  - [ ] Glassdoor via Fetchlayer, which scrapes Glassdoor. This connector is not built until it is
    cleared.
- [ ] **Rotate every API key** that was pasted into chat during the build: NVIDIA, Groq, Azure
  OpenAI, Tavily, GNews, YouTube, EPO, Alpha Vantage, Fincrux and Fetchlayer. In deployed
  environments, move them to Key Vault (`*_kv_uri` settings).
- [ ] **Review the watchlist.** Apollo Tyres was approved only in a local dev database, to test the
  pipeline. Any real approval is a compliance decision.
- [ ] **Push and review.**
  - [ ] Push commit `e885d4b` on `dev_sow`.
  - [ ] Raise the PR against `main`. On this machine, run `gh auth login` first, or use
    https://github.com/zenpd/rpg_horizon_radar/pull/new/dev_sow.

## 2. Make more of the data real

| Item | Today | To do |
|---|---|---|
| Rivals for KEC, Zensar, RPG Life Sciences, Raychem, Harrisons | "Rival A"-style placeholders with an invented timeline, customer voice and analyst view | Open their gates after sign-off, run discovery, then approve companies in Admin → Watchlist |
| More CEAT rivals | Only Apollo Tyres is approved | Review MRF, JK Tyre, Bridgestone India and Goodyear India (already proposed) |
| Strengths and weaknesses (all companies) | Demo "strategy team list" (`app/radar/data/swot.json`) | Add a screen where each strategy team edits its own list; store it in a table |
| Deal targets (Meridian, Strata, Sensa …) | Fictional: signals, financials, ownership graph, scenarios | Choose a source, or feed approved watchlist companies into the deal desk; then retire the fictional set |
| Market performance | Synthetic price series | Use Alpha Vantage daily prices for the approved rivals (25 calls a day) |
| Rival deals database | Demo list | Source from NSE takeover/SAST filings and news deal headlines (`deal_activity` signals) |
| Competitors roster | Demo | Build it from the watchlist (approved and proposed companies per RPG company) |
| Ask Radar | Keyword rules over demo data | Answer over live signals; fix Azure access (below) |
| Deep dive | Simulated progress timer and pre-written book pages | Real research step per case, at least a live-signal summary and filings |
| Follow-up "simulate next week" | Scripted updates | Show new live signals for the case's company since approval |
| NewsData.io, Adzuna | Built but off (no keys) | Add `NEWSDATA_API_KEY`, `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` |
| Azure gpt-4.1-mini | HTTP 403 (public network access disabled), so thesis parsing and Ask Radar fall back to rules | Private endpoint or allowed network for the API's host |
| Fictional seed entities on the Signal board | Mock connectors, by design | Keep for the demo, or hide them once enough real companies are approved |

## 3. Persistence and platform

- [ ] **Move the radar's in-memory state to the database.** Today the book, decisions, plans,
  follow-ups, theses, watch rules, universe and activity feed live in `app/radar/store.py` and are
  lost on restart. Only agent SWOTs (`swot_briefs`) and live data persist.
- [ ] **Run migration `0003_live_signals` on PostgreSQL** (upgrade and downgrade). It has only been
  tested on SQLite.
- [ ] **Background work across replicas.** Replace the in-process scheduler with a Temporal
  Schedule on `IngestionWorkflow`, or run it in one replica only. Background jobs are in memory too.
- [ ] **Deployment settings.** Add the new settings to the ACA environment and the pipelines:
  connector keys, `LLM_ROUTES`, `SCHEDULER_ENABLED`, `INGEST_DAILY_AT`, `DISCOVERY_EVERY_DAYS`,
  `AUTO_SWOT`.
- [ ] **Quiet tracing locally.** Phoenix tracing is noisy when no collector is running (local and
  tests). Skip the exporter when the collector is unreachable or a flag is off.
- [ ] **CI.** Run `pytest` (app) and `npx tsc --noEmit` / `vite build` (app/ui) on every PR.

## 4. Code and tests

- [ ] **Port the remaining prototype tests:**
  - [ ] LLM route behaviour (rate-limit waits, schema-rejection retry, fallback to the next route),
    against `shared/llm_chat.py`.
  - [ ] Azure thesis parsing and Ask Radar fallbacks.
- [ ] **Review the Escalation Brief wording** now that it can name real companies (DESIGN.md §14).
- [ ] **Dark theme for the desk screens.** The Restricted desk screens (Signal board, Digests, Admin)
  stay light in dark theme; theme them if needed.
- [ ] **One place to manage the watchlist.** Admin → Watchlist and Radar settings → Watched
  companies both show watchlist information. Decide which screen owns approvals.
- [ ] **Archive the old prototype folder** (`Claude outputs/RPG_Horizon_Radar`) once the team is on
  this repo. Its live caches and `.env` are local only.

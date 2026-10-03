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

- [x] **Move the radar's in-memory state to the database.** `app/radar/store.py`'s cases (stage,
  decision, plan, updates, outcome), book order, followed rivals, activity feed, theses, triggers
  and universe now round-trip through the existing `connector_state` table
  (`radar/persistence.py`, keyed `radar_mutable_state`) — one snapshot, saved after every mutation
  (`Store.audit()`/`Store.persist()`), restored once at boot after `radar/bridge.py`'s own
  (unpersisted) startup reset. Verified end-to-end: escalated a case through deep-dive to the
  book, added a thesis/trigger/universe entry, toggled a trigger off, killed and restarted the
  process against real Postgres — all of it was still there. Deliberately NOT persisted: agent
  SWOTs (already in `swot_briefs`), and the deep-dive progress-animation jobs themselves (their
  only lasting effect — stage/in_book — is covered by the cases snapshot).
- [x] **Run migration `0003_live_signals` on PostgreSQL** (upgrade and downgrade). Tested directly:
  both directions apply cleanly.
- [ ] **Background work across replicas.** Replace the in-process scheduler with a Temporal
  Schedule on `IngestionWorkflow`, or run it in one replica only. Background jobs are in memory too.
  Not attempted this pass — a real architecture change, not a quick fix.
- [x] **Deployment settings.** Added to `infra/aca-setup.sh` and `azure-pipelines-be.yml`:
  `SCHEDULER_ENABLED`, `INGEST_DAILY_AT`, `DISCOVERY_EVERY_DAYS`, `AUTO_SWOT`, `LLM_ROUTES` as
  plain values; every connector/LLM key as a `*_KV_URI` setting (new fields + `kv_map` entries in
  `shared/config.py`, matching the existing Azure OpenAI pattern) — wired to Azure Pipelines
  variable-group placeholders rather than inline secrets, since real Key Vault URIs still need
  creating as part of the key-rotation item above.
- [x] **Quiet tracing locally.** `observability/tracing.py` now probes the collector (0.3s TCP
  connect) before configuring the exporter, and skips entirely on a miss — no more background
  retry noise. A new `TRACING_ENABLED` flag (`tests/conftest.py` sets it false) covers the rest.
- [x] **CI.** `.github/workflows/ci.yml` runs `pytest` (app) and `npm run build` (`tsc --noEmit` +
  `vite build`, app/ui) on every PR and on push to `main`/`dev_sow`. No secrets needed —
  `tests/conftest.py` already points everything at a throwaway SQLite file with every external key
  blank.

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

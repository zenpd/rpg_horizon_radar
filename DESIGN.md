# RPG Horizon Radar — HLD, Architecture & Delivery Design

Source submission: `19_RPG_Horizon_Radar.docx` (RPG Innovation Festival 2026)
Category: Cross-Subsidiary AI/ML Innovation — Corporate Strategy (Restricted Access)

---

## 1. Executive Summary

Horizon Radar is a **signal-surfacing agent**, not a valuation or due-diligence tool. It continuously
scans public information (news, regulatory filings, patent activity, hiring patterns) across the
sectors RPG's subsidiaries operate in, correlates weak signals into a distress/opportunity score, and
routes a small number of genuinely notable items to a **named, restricted Corporate Strategy reviewer
list** as a weekly digest.

The design center of this system is **not** the scanning/scoring pipeline — it's the access-control and
audit boundary around it. Every architectural decision below is subordinate to one rule taken directly
from the source doc: *the tool's job stops at flagging; the moment a signal becomes "under active
evaluation" it exits the AI system and enters RPG's existing formal, restricted M&A process.*

## 2. Problem Statement

- Weak signals of M&A opportunity or competitive risk (leadership churn, delayed filings, credit
  actions, patent/hiring shifts) are public but scattered across dozens of sources per sector.
- Today they're found late — usually via an external banker/advisor — because tracking them manually
  across tyres, EPC, IT, pharma, materials, and plantations doesn't scale.
- The fix is detection speed, **not** a new decisioning system: Corporate Strategy still evaluates and
  decides, through the existing formal process.

## 3. Scope & Non-Goals

**In scope:** ingesting public signals, correlating them per entity, scoring distress/opportunity,
routing to the relevant subsidiary context, compiling a restricted weekly digest, full audit logging,
a named reviewer allow-list, and a clean hand-off point into the formal M&A process.

**Explicitly out of scope (non-goals):**
- No valuation, deal-modeling, or due-diligence output — signals only.
- No autonomous outreach or autonomous action of any kind.
- No integration with RPG NeuralMesh or any subsidiary-facing search/chat/shared index. This system's
  outputs never enter a shared or subsidiary-visible store.
- No decisioning — once a signal is marked "under active evaluation," the tool's involvement ends.

## 4. Access Model

There are no roles, no sector gates and no approval steps (migration `0005_remove_approvals`). Earlier
versions had a `compliance_admin` role, per-subsidiary reviewer scopes, a `compliance_gate` per sector
and an approval step for every watched company; all were removed at the team's request (7 Oct 2026).

| Control | Implementation |
|---|---|
| Named users, no signup | Every user is a row in the `reviewer` table, added by another signed-in user. The first one comes from `FIRST_USER_EMAIL` / `FIRST_USER_PASSWORD`. There is no self-service signup. |
| Everyone sees everything | Every signed-in user sees every RPG company, signal, digest and watched company, and can change the watchlist, the user list, and the radar's cases, theses and rules. |
| No shared-index integration | Horizon Radar has its own isolated data store. It is never a data source for NeuralMesh, BrandPulse, or any other submission in this set. |
| Activity history | Every view of a signal, entity, digest or radar screen, and every change, is written to an `audit_log` row: who, what, when. Every user can read it (Users and watchlist → Activity); no endpoint deletes it. |
| Explicit exit from AI scope | Marking a signal "Under Active Evaluation" is a one-way, recorded action. Once set, the signal drops off the live board — the system's involvement is over. |

This is why Horizon Radar is a **separate submission from BrandPulse**: BrandPulse's audience is wide
and subsidiary-local (marketing reviewers); this system's audience is Corporate Strategy, often under a
formal information barrier that includes marketing. Sharing a data store or
workflow between the two would create exactly the leak vector the doc calls out.

## 5. High-Level Architecture

```
 ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │ News / press  │   │ Filings /    │   │ Patent       │   │ Hiring       │      Signal-ingestion
 │ connector     │   │ annual report│   │ activity     │   │ pattern      │      agents (per source
 │ (pluggable)  │   │ connector    │   │ connector    │   │ connector    │      type, one per sector)
 └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
        └──────────────────┴──────────────────┴──────────────────┘
                                    ▼
                        ┌───────────────────────┐
                        │  Raw Signal Store      │  (isolated DB — never shared)
                        │  entity-linked, sourced│
                        └───────────┬───────────┘
                                    ▼
                        ┌───────────────────────┐
                        │ Distress/Opportunity   │  Flags co-occurring signals
                        │ Scoring Agent          │  on the same entity, not
                        │ (rule-based + LLM      │  single headlines
                        │  rationale hook)       │
                        └───────────┬───────────┘
                                    ▼
                        ┌───────────────────────┐
                        │ Relevance-Routing Layer│  sector/category → subsidiary
                        └───────────┬───────────┘
                                    ▼
                        ┌───────────────────────┐
                        │ Weekly Digest Compiler │
                        └───────────┬───────────┘
                                    ▼
        ┌───────────────────────────────────────────────────────┐
        │            LOGIN (named users, no roles)               │
        │   every read → audit_log(user, resource, action, ts)   │
        └───────────────────────────┬───────────────────────────┘
                                    ▼
                        ┌───────────────────────┐
                        │ Corporate Strategy UI  │  digest / signal detail /
                        │ (signed-in users)      │  "mark under evaluation"
                        └───────────┬───────────┘
                                    ▼
                  Exits AI scope → RPG's existing formal,
                  restricted-list M&A process
```

## 6. Data Model

| Entity | Purpose |
|---|---|
| `subsidiary` | CEAT, KEC International, Zensar, RPG Life Sciences, Raychem RPG, Harrisons Malayalam — each with its sector tags. |
| `source_connector` | Registered ingestion connector (news / filings / patents / hiring), sector-scoped. |
| `raw_signal` | One ingested fact: entity, signal_type, headline, source_url, source_excerpt, observed_at. Immutable. |
| `entity` | A watched company/asset with sector/category tags used for routing. |
| `signal_cluster` | Group of `raw_signal` rows on the same entity within a rolling window — the unit the scoring agent evaluates. |
| `opportunity_score` | Composite score + rationale + contributing signal types for a cluster. |
| `routing_rule` | sector/category → subsidiary mapping (seeded from the doc's table). |
| `reviewer` | Named user: name, email, password hash. No roles, no open registration. |
| `digest_issue` | One weekly digest: period, items (scored clusters above threshold), recipients. |
| `audit_log` | The activity history: reviewer_id, action (`view_signal`, `view_digest`, `mark_under_evaluation`, `user_change`, `watchlist_change`, …), resource type/id, timestamp. |

## 7. Agent Design

Horizon Radar has two kinds of moving parts, kept in two places:

- **LLM agents** live in `app/agents/`. They are the only code that calls a language model.
- **The signal pipeline** lives in `app/services/` and `app/ingestion/`. It is rule-based by design, so
  every score, route and digest can be traced to a constant or a rule.

No LLM agent scores a signal or values a company. Discovery's picks go straight onto the watchlist
(anyone can remove one); the SWOT Analyst's and Opportunity Analyst's drafts are rule-checked before
they are shown.

### 7.1 LLM agents (`app/agents/`)

| Agent | Module | What it does | Guardrails |
|---|---|---|---|
| **SWOT Analyst** | `swot_analyst.py` | For one RPG company, drafts the SWOT and TOWS moves from numbered public evidence: public facts about the company itself (`services/company_research.py`: quarterly results, shareholding, web and news) for strengths and weaknesses, and those facts plus its watched companies' signals for opportunities and threats. It also cites the daily findings users kept in the last week. What it reads and the analysis factors it tags every item with follow the company's **SWOT parameters** (`services/swot_settings.py`). Runs every `SWOT_EVERY_DAYS` (default 7) for all six, refreshing their research first, or when a user builds or rebuilds one. | Rule checks on every draft (item counts, every item tagged with a ticked factor, strengths and weaknesses cite research on the company, every citation exists, at most one move per watched company, every move links a strength/weakness to an opportunity/threat, act-now items drive a move, no ids in prose, scores not gamed). A failing draft goes back to the model with the problems listed, up to 3 drafts; if none passes, the current SWOT stays. |
| **Acquisition Thesis** | `acquisition_thesis.py` | For every M&A signal, in the background (and on Rewrite thesis): researches the company (results, shareholding, web pages on six factors including ownership and group structure, news), then writes its background, its connections (shareholders, parent, subsidiaries, joint ventures, partners), its SWOT, a comparison with the RPG company's SWOT, a fitment analysis (strategic, product, market, capability, scale, risk), a post-acquisition SWOT, the ripple effect on the other five RPG companies, partial or full acquisition, and open questions (§14). Kept up to date: rewritten straight after a news run that brings the target new signals, after the RPG company's SWOT is rebuilt (weekly or Build SWOT), after discovery, and at least weekly. | Every point cites numbered evidence; one fitment entry per dimension and one ripple entry per other company; a rating other than unknown needs evidence; comparison points link only to real SWOT items; no ids in prose; no valuation. Same revise loop as the SWOT Analyst. |
| **Sector Scout** | `sector_scout.py` | Daily, right after the news run (and on Scan industry news now): reads the last 7 days of each RPG company's industry news (funding rounds, stake sales, distress, deals, contract wins — GNews, else Tavily news) and picks the smaller companies in it the RPG company could buy, with the event and why. Each is sized: too big is set aside; the rest are watched as targets (or matched to a watched company) with the news items as their public signals, so they appear on M&A Signals ("Found in sector news") and get a thesis. | A company counts only when a cited item names it; no RPG company, large or listed company near the RPG company's size, or company already being bought by someone else; up to 8 a run. |
| **Ask Radar** | `ask_agent.py` | On each question in an Ask Radar conversation: gathers the radar's own data on the companies the question (or the conversation) names and the selected company — signals and score, size, thesis, competitor overview, SWOT, the week's findings, financial health, the scoring rules — as numbered evidence (R1 ...), answers from it, and only when that does not answer the question searches the web (Tavily, else DuckDuckGo; W1 ...) and answers again. Conversations are saved per user (`chat_threads`, `chat_messages`, migration 0008) and are private: every read and write is filtered on the user. | Every fact cited in square brackets; cited ids must exist; an uncited answer goes back up to twice and is then marked unverified; no valuation, deal price or recommendation to bid; web results kept only when they contain most of the query's words and have a real link. |
| **Competitor Profile** | `competitor_profile.py` | For every watched company with public signals, in the background (and when an overview is opened or on Rewrite overview): reuses the Acquisition Thesis agent's research on it and writes a summary, its SWOT, how it competes with the RPG company (ahead, behind, head-to-head, linked to the RPG company's SWOT), the competitive intensity (high, medium, low; how hard it competes with the RPG company) and what to watch. Shown on Competitor Analysis → Overview with its recent moves (deals and ownership, patents, hiring and leadership, results and filings, news) and its results and shareholding. Rewritten when its signals change, the RPG company's SWOT is rebuilt, or weekly. | Every SWOT item and competition point cites evidence; 1-4 items per quadrant, 2-6 competition points, 1-4 things to watch; SWOT references must exist. Competitor Analysis cards show the rule-based score as "Competitive intensity" (the same calculation as the opportunity score, explained behind its "i"); the agent's high/medium/low judgement is shown as "Overall" on the overview; no ids in prose. Same revise loop as the SWOT Analyst. |
| **Opportunity Analyst** | `opportunity_analyst.py` | Daily, right after the news run, for each RPG company: reads the last two days of news about the company, its watched companies (and their new signals) and its industry (the sector searches in its SWOT parameters), and reports the opportunities and threats it creates, each with the SWOT item it affects (or "new"), the effect, impact and urgency, a next step and its sources. Users keep or dismiss each on This week; kept ones feed the next weekly SWOT. Also on demand (Run now). | At most 6 findings; every finding cites the news; the SWOT item must exist; no ids in prose; a finding already reported in the last 7 days is rejected, and news already cited is not read again. Same revise loop as the SWOT Analyst. |
| **Target Discovery** | `target_discovery.py` | Weekly with watchlist discovery (or on Find rivals now): for each RPG company, web searches for smaller players in its segment, distress or promoter stake-sale situations, and its saved acquisition theses; the model picks up to 5 companies the RPG company could plausibly buy. Each is watched with role `target` and sized (`services/company_size.py`); one larger than half the RPG company is set aside (dismissed) with the reason. | The same grounding check as watchlist discovery; it must not pick market leaders, large listed companies, RPG Group companies, conglomerates or multinationals; the size check overrides the model. |
| **Watchlist discovery** | `watchlist_discovery.py` | For each subsidiary, runs two Tavily web searches and asks the model for up to 5 competitors or adjacent players, with a reason and the results that name each one. Runs weekly, or on demand. | A grounding check keeps only names that appear in the results the model cites. New companies are watched at once; a company someone removed is never added again. |

All three draft through **`llm_routes.py`**: schema-constrained JSON from Groq `openai/gpt-oss-120b` (low
reasoning effort), then NVIDIA Nemotron 3 Super, then the Azure OpenAI deployment. It waits out rate
limits, moves to the next route on errors or oversized requests, and retries once in plain JSON mode
when a provider rejects its own schema-constrained output.

**`llm_azure.py`** makes single calls to the Azure OpenAI deployment (gpt-4.1-mini) for two small helpers
that are not agents: turning a plain-language acquisition thesis into search criteria, and the old
one-shot Ask endpoint (`/ask`, no longer used by the screen: Ask Radar is now the Ask Radar agent). Each
has a rule-based fallback in its caller, and after a failure Azure is skipped for 5 minutes.

### 7.2 The signal pipeline (rule-based, `app/services/` and `app/ingestion/`)

1. **Signal ingestion** — one connector per source. Connectors implement
   `fetch(entity, since) -> list[RawSignal]`; every one is a live source read for the watched companies (§15).
2. **Distress/opportunity scoring** (`services/scoring.py`) — each signal type has a base weight;
   **co-occurrence within a window is scored super-linearly**, so "leadership churn + delayed filing +
   credit downgrade" scores far above three isolated headlines. The rationale string is a template.
3. **Relevance routing** (`services/routing.py`) — matches a scored cluster's entity sector/category tags
   against `routing_rule` to attach it to the right subsidiary or subsidiaries.
4. **Digest compiler** (`services/digest.py`) — weekly job that selects clusters above the score
   threshold per subsidiary and builds a `digest_issue`. No autonomous outreach — a user must log in to
   see it.

## 8. Access Control & Security Architecture

- **AuthN:** email/password against the `reviewer` table only; no self-registration endpoint exists
  at all. Session token (JWT) on login.
- **AuthZ:** none beyond the login: every signed-in user can do everything (§4).
- **Activity history:** every `GET` on a signal, digest or radar screen, and every change, is recorded
  with the signed-in user — no exceptions, no opt-out.
- **Isolation:** separate database, separate deployment, no shared API surface with NeuralMesh or any
  other submission's backend. This is enforced structurally (different repo/service), not by
  configuration that could drift.
- **UPSI framing:** every screen carries a persistent "Restricted — UPSI-adjacent — do not forward"
  banner, reinforcing handling expectations.

## 9. End-to-End Flow (the CEAT cascade from the doc)

1. **Trigger** — ingestion agent detects a regional tyre-components supplier with concurrent signals:
   leadership departures, a delayed quarterly filing, a credit-rating downgrade.
2. **Scoring** — the co-occurrence bonus pushes this cluster's score well above any single-signal item.
3. **Routing** — tagged `tyres/mobility` → routed to CEAT. A second, unrelated cluster (EPC competitor
   project distress) routes to KEC in the same digest run.
4. **Digest** — both appear in the next weekly digest, under their subsidiaries. The view is recorded.
5. **Hand-off** — a user marks the CEAT item "Under Active Evaluation." It disappears from
   the live board; the formal M&A process takes over from here, outside this system entirely.

## 10. Implementation Architecture (this build)

Rebuilt on the **ZenLabs Agent Foundry accelerator template** (`accelerator-bootstrapper-template`) —
the same standard structure behind `digital-onboarding`, `zenarc`, `merchant-onboard`, and
`capmarkets` — so this app is consistent with how the rest of the org's agentic apps are built,
deployed, and operated: **FastAPI (async) + PostgreSQL (SQLAlchemy async + Alembic) + Redis +
Temporal (durable workflows) + OpenTelemetry/Arize Phoenix observability + Azure Key Vault**, with a
**React + Vite + Tailwind (TypeScript)** UI served by nginx, deployable to Azure Container Apps.

**Where Horizon Radar diverges from the template:** the accelerator ships a LangGraph supervisor-loop
example (a chat/session "Playground", its router, Temporal workflow, prompts and LangChain client).
Horizon Radar has removed it. Its two LLM agents (§7.1) are each a short draft → check → revise loop
over plain HTTP model calls, which a graph framework would add weight to without adding control, and
they live in `app/agents/` in place of the example. Scoring stays rule-based and auditable, never an
LLM call (§7.2, §14). The one piece of platform infra the pipeline uses for real is **Temporal** — the signal-ingestion
pipeline runs as `IngestionWorkflow` (durable, retried on transient failure) rather than a plain
in-process function call, which is the accelerator's "Durability with Temporal" pattern applied to
what this app actually needs durability for. `POST /api/v1/ingest/run` starts that workflow, falling
back to an inline call only if Temporal/the worker isn't reachable (e.g. running the API alone without
`docker compose up`), so ingestion still works with the lighter local setup.

```
rpg_horizon_radar/
├── DESIGN.md                       ← this document
├── docker-compose.local.yml        Postgres + Redis only (lightweight local dev)
├── infra/aca-setup.sh              Azure Container Apps provisioning
├── azure-pipelines-{be,fe}.yml     CI/CD — build & deploy on push to main
├── .github/workflows/ci.yml        pytest + UI build on every PR
└── app/
    ├── api/
    │   ├── main.py                  FastAPI app, CORS, startup seed, router registration
    │   ├── auth.py                  named-reviewer JWT (replaces the template's EntraID stub —
    │   │                            see DESIGN.md §4/§8; there is no signup endpoint anywhere)
    │   ├── dependencies.py          Redis + async DB session dependencies
    │   ├── routers/                 auth, subsidiaries, entities, signals, digests, ingest, jobs,
    │   │                            watchlist, reviewers, audit-log, health
    │   └── schemas/                 Pydantic request/response models
    ├── agents/                      the LLM agents and their model clients (§7.1)
    │   ├── swot_analyst.py          SWOT Analyst: draft → rule checks → revise
    │   ├── opportunity_analyst.py   Opportunity Analyst: the day's news against the SWOT
    │   ├── watchlist_discovery.py   web search → model picks → grounding check → watchlist
    │   ├── llm_routes.py            Groq → NVIDIA → Azure OpenAI routes for both agents
    │   └── llm_azure.py             one-shot Azure calls for thesis parsing and Ask Radar
    ├── radar/                       the radar screens' API, /api/v1/radar (§16)
    ├── workflows/
    │   ├── ingestion_workflow.py    IngestionWorkflow — Horizon Radar's Temporal usage
    │   └── activities.py            run_ingestion_activity
    ├── workers/worker.py            registers IngestionWorkflow
    ├── db/
    │   ├── models.py                Subsidiary, Entity, RawSignal, SignalCluster,
    │   │                            OpportunityScore, ClusterSubsidiaryLink, Reviewer,
    │   │                            DigestIssue/Item, EscalationBrief, AuditLog,
    │   │                            ConnectorState, SwotBrief
    │   └── seed.py                  the six subsidiaries and the first user
    ├── alembic/versions/            0001 (template baseline), 0002 (Horizon Radar schema),
    │                                0003 (live signals, §15), 0004 (removes the demo data),
    │                                0005 (removes roles, sector gates and watchlist approval),
    │                                0006 (opportunity_findings)
    ├── ingestion/connectors/        base.py, live/ (the public sources, §15)
    ├── services/                    the rule-based pipeline (§7.2) and its plumbing
    │   ├── scoring.py                co-occurrence-weighted scoring + templated rationale (no LLM)
    │   ├── routing.py                sector/category → subsidiary
    │   ├── company_research.py       public facts on the RPG companies themselves, and the daily news
    │   ├── swot_settings.py          each company's SWOT parameters (sources, factors, sector searches)
    │   ├── ingest.py                 shared by the Temporal activity and the inline fallback
    │   ├── pipeline.py               an ingestion run: Temporal or inline, then SWOT rebuilds
    │   ├── scheduler.py              daily ingestion, weekly discovery (one replica, via lease.py)
    │   ├── jobs.py, lease.py         background jobs and cross-replica leases
    │   ├── digest.py                 weekly digest compiler
    │   └── audit.py                  activity history writer
    └── ui/src/
        ├── radar/                    the radar screens (§16) — the app's main UI
        ├── pages/                    Login, Dashboard, SignalDetail, DigestArchive, Admin (users and watchlist)
        ├── components/               RestrictedBanner, SignalCard, ScoreBadge, EscalationBrief, …
        │   └── layout/              Sidebar, Header, Footer, AppShell — see UI theme note below
        └── services/api.ts           axios client, typed against api/schemas
```

**UI theme:** the ZenLabs Design System (Plus Jakarta Sans, white cards on gray-50, the shared
`.card`/`.btn-*`/badge component classes) is ported from `digital-onboarding`, another Agent Foundry
app, so Horizon Radar looks and feels consistent with the rest of the org's agentic apps rather than
being a one-off. The one deliberate departure: Horizon Radar's own primary actions and logo mark use a
rose "restricted" gradient in place of the shared indigo "zen" gradient — a visual cue, carried through
the sidebar, buttons, and the persistent restricted-access strip under the header, that this is the
UPSI-adjacent, access-restricted app and not a generic product surface.

Deployment note: every user of a deployment sees all of its data, so for the actual pilot this should
run in RPG's restricted network segment, with accounts only for Corporate Strategy — not on
shared/public infrastructure. `infra/aca-setup.sh` and the Azure
Pipelines are the template's standard path to Azure Container Apps; using them for a real pilot still
requires the network/access scoping above, which is outside what the pipeline itself enforces.

## 11. MVP / Phase 1 — Delivery Plan (as specified in the submission)

1. **Pilot sector:** CEAT (tyres/mobility) first, though every subsidiary's watched companies are
   ingested.
2. **Validate:** scoring, routing and the watchlist are tested on real-shaped fixtures in the test
   suite (`app/tests/`). The seeded mock signals of earlier versions were removed (migration 0004).
3. **Feedback loop:** one pilot weekly digest to the Corporate Strategy group.

## 12. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| User list creep ("just add me") | Any user can add users, so who holds an account is a team decision; every change is in the activity history. |
| Signal reaching the wrong subsidiary | Routing is explicit table-driven (`routing_rule`), not inferred per-request — auditable and correctable without touching scoring logic. |
| Tool drifting into a decisioning role | The radar shortlists and writes theses; it never decides. A thesis carries no valuation and says it is not a recommendation to bid. |
| A company watched that should not be | Discovery adds companies at once; anyone can remove one, and discovery never re-adds it (§15). |
| A model inventing a company or a fact | Discovery keeps only names found in the search results the model cites; the SWOT Analyst's drafts are rule-checked against their numbered evidence and never feed scores (§15). |

## 13. Success Metrics (for the pilot)

- Time-to-detection for a known past distress/opportunity event, measured against when it became
  public knowledge (target: materially earlier, matching the doc's "weeks before either became public
  knowledge" framing).
- Reviewer-rated signal relevance (kept/escalated vs. dismissed) during the CEAT pilot.
- Every signal/digest read has a matching `audit_log` row.

## 14. Addendum — Acquisition thesis (replaces the Escalation Brief)

Earlier versions wrote a templated **Escalation Brief** (pros, cons, directional considerations) when a
`compliance_admin` marked a signal "under active evaluation". Both were removed on 7 Oct 2026: each M&A
signal now has a detailed **acquisition thesis**, written by the Acquisition Thesis agent
(`agents/acquisition_thesis.py`, §7.1) in the background for every signal not in the archive — on the
daily run that brings the signal (scheduler job `theses`, and right after a manual ingestion run) and
again when it is a week old — and users shortlist or dismiss signals instead of handing them off. The `escalation_briefs` table and its old rows are kept, unused.

**Contents** (every point cites numbered public evidence about the target):

| Section | What it says |
|---|---|
| Headline | One sentence on what the deal would do for the RPG company |
| Company background | A summary and 2-6 cited points on its business, history, products, scale, ownership and management |
| Connections | Shareholders and promoter group (with stakes when stated), parent, subsidiaries, joint ventures, partners, key customers and suppliers, directors — drawn as a graph around the company, with an RPG company or a watched company among them flagged. Only links public sources state; full shareholder registers (MCA) are not a source |
| Partial or full acquisition | full, partial or unclear, with the reason (promoter stake sales, control, relative size) |
| SWOT comparison | The target's own SWOT next to the RPG company's current SWOT, and where the target complements, overlaps with or conflicts with it (linked to the RPG company's SWOT items) |
| Financial health | Rule-based, not written by the agent: the target's published figures beside the RPG company's (results and growth, debt to equity, interest cover, free cash flow, ROCE, Altman Z-score, promoter holding) and the level to expect after a deal — the average of the last 8 quarters, which for smaller deals predicted the target's figures afterwards (Dogan and Ugurlu, 2024). A private target says it publishes no accounts. Each M&A signal card carries a one-line balance-sheet summary |
| Post-acquisition SWOT | The RPG company's SWOT as it would look after the deal, 1-4 items per quadrant, each marked new (from the target, cited), strengthened or weakened (a current SWOT item the deal changes, cited) or carried over (a current item it leaves as it is) |
| Fitment analysis | Strategic, product, market, capability, scale and risk fit, each strong / moderate / weak / unknown with its reasoning; scale compares the target's size with the RPG company's own results |
| Ripple effect | For each of the other five RPG companies: opportunity, neutral or risk, and why (supplier and customer links, shared customers and markets) |
| Open questions | What a diligence team must answer first |

**The hard line stays:** no valuation, price, multiple or synergy figure, and it is labelled a draft
for review, not a recommendation to bid. Stored per signal and RPG company in `connector_state`
(`thesis:<case>:<code>`); the target's research is reused for a week (`research:entity:<id>`).

## 15. Addendum — Live signals on real companies

**History.** The original build allowed only fictional watched entities (a DB CHECK,
`is_fictional = true`), seeded with invented signals. Migration `0003_live_signals` lifted that CHECK
and added an approval workflow (a `compliance_admin` approved each proposed company, per open sector
gate). Migration `0005_remove_approvals` removed that workflow, the gates and the roles (§4).

| Rule | Implementation |
|---|---|
| Found companies are watched at once | `Entity.status`: `watching` or `dismissed`. Discovery and manual additions create `watching` companies, with `watched_since`; only `watching` entities are ingested (`services/ingest.py`). |
| Removed stays removed | Anyone can remove a company (`dismissed`); weekly discovery never re-adds it, and anyone can watch it again. Every change is a `watchlist_change` row in the activity history. |
| Scoring stays rule-based | New signal types get fixed weights in `services/scoring.py`; no model is involved. |
| Public data only | Every live connector reads public APIs or exchange disclosures; nothing non-public is ingested. The UPSI banner and the activity history apply unchanged. |

**No demo data.** Migration `0004_remove_demo_data` removed the fictional companies with everything
derived from them (signals, clusters, scores, digest items, escalation briefs), every SWOT brief (all
were drafted from a demo strategy-team list and demo deal targets), the radar's saved demo state and
the `is_fictional` column, and disabled the demo logins (kept as rows so the audit trail stays whole).
The app now seeds only the six subsidiaries and the first user, from `FIRST_USER_EMAIL` /
`FIRST_USER_PASSWORD`. A screen with no real source says so instead of showing invented data.

**Live connectors** (`ingestion/connectors/live/`, keys in `app/.env`; a connector without a key is
skipped). Each emits a signal only past a stated threshold — routine notices, flat readings and
unrelated headlines are dropped, not stored:

| Connector | Reads | Signal types emitted | Pace / quota |
|---|---|---|---|
| NSE (no key) | corporate announcements (21 days), promoter pledges | leadership_churn (resignation/cessation only), auditor_change, credit_downgrade (downgrades only), delayed_filing, legal_action, deal_activity, fund_raise, promoter_pledge (≥ 5%) | 2 calls/company/run, 1 s apart; `NSE_ENABLED=false` turns it off — NSE's terms restrict automated access |
| Fincrux | quarterly and annual results, balance sheet, cash flows, ratios, shareholding | earnings_decline (net profit ≤ −15% or sales ≤ −10% YoY), stake_selldown (promoters −0.5 pt or FIIs −1.5 pt), balance_sheet_stress (weight 25: Altman Z-score below 1.81, debt above 2× equity, or interest cover below 1.5×; `services/market_data.health`) | weekly per company; hard stop at 5 calls/day |
| Alpha Vantage | BSE daily prices; ticker search | share_price_slump (≤ −20% over 30 trading days) | daily; hard stop at 25 calls/day |
| GNews, GDELT, NewsData.io, Tavily, DuckDuckGo, YouTube | headlines / video titles naming the company (GDELT: Indian English-language outlets, 14 days, no key) | headline classifier → credit_downgrade, delayed_filing, legal_action, leadership_churn, hiring_scaledown, promoter_pledge, deal_activity, press_distress, press_opportunity | every run; GNews spaced 1.5 s; GDELT one request every 6 s (it refuses more, and can refuse a shared office or VPN address); `GDELT_ENABLED=false` turns it off. DuckDuckGo (`services/web_search.py`, the open-source `ddgs` library, no official API, paced 3 s) answers every news and web search Tavily refuses — the rest of that day goes straight to it — but never a size check: a size comes only from Tavily's sourced answer or Fincrux's exchange market cap (preferred for listed companies), else the company is shown as "Size not verified"; `DDG_FALLBACK=false` turns it off |
| Adzuna | job postings (30 days) | hiring_scaleup / hiring_scaledown (×1.5 / ×0.5 vs. last reading, ≥ 20 postings) | weekly |
| EPO OPS | patent publications (last 6 months vs. the 6 before) | patent_shift (×2 or ×0.5, ≥ 5) | weekly |

NSE symbols are resolved automatically (Alpha Vantage ticker search confirmed by NSE, else a Fincrux
name search; a miss is retried weekly) or set by hand on the watchlist. Pacing, budgets and
snapshots persist in the `connector_state` table. Glassdoor (via Fetchlayer) is not wired: it scrapes
Glassdoor, which needs a licence check first.

**Watchlist discovery** (`agents/watchlist_discovery.py`): per subsidiary, two Tavily searches, then a
reasoning model picks up to 5 competitors / adjacent players, and a grounding check keeps only names that
appear in the results it cites. The model picks names; it never scores. Each company carries the
model's one-line reason and the source links, shown on the watchlist.

**SWOT** (the radar's SWOT Analyst, `agents/swot_analyst.py`; see §16): per RPG company, an LLM drafts the
SWOT and TOWS moves from numbered public evidence — research on the company itself for strengths and
weaknesses, and that research plus its watched companies' signals for opportunities and threats. Rules then
check it (counts, strengths and weaknesses cite research on the company, citations exist, every move links a strength/weakness to an opportunity/threat,
act-now items drive a move, no ids in prose, scores not gamed). Failures go back to the model for
revision (up to 3 drafts); a draft that never passes leaves the current SWOT in place. Each item shows
its reasoning and cited sources. It carries no valuation and never changes a score.
Rebuilds are stored in `swot_briefs` and reloaded at startup. A company that watches no company with
signals gets a SWOT without moves.

**Company sizes** (`services/company_size.py`, no model): market capitalisation (listed companies) and
annual revenue (any company) in ₹ crore, read from a Tavily search answer and kept with that answer and its
first source link, refreshed monthly (`size:entity:<id>`, `size:rpg:<code>`). NSE's quote API is blocked
from this network, Fincrux allows 5 calls a day and Alpha Vantage rarely covers Indian fundamentals, so a
search answer is the practical source; each figure shows its source so it can be checked. A company is
compared with an RPG company on market cap when both have one, else on revenue.

**Headline classifier** (`ingestion/connectors/live/common.py`): a headline about sport, sponsorship,
awards or a hobby video (a rally or race a tyre maker sponsors, a chess league, an RC model) is never a
signal, and "wins"/"bags"/"secures" count only with an order, contract or project, "launch" only with a
product, plant or service.

**Research on the RPG companies** (`services/company_research.py`, no model): for each of the six,
Fincrux's latest quarter against a year earlier, the last four quarters against the four before, and
the shareholding pattern (listed companies; it shares the connectors' 5-calls-a-day budget); one Tavily
web search per ticked analysis factor, and 30 days of news; and GNews headlines — each only when its
source is ticked in the company's SWOT parameters. Only items that
name the company are kept; the same story from several outlets is kept once (headline word overlap);
social posts, scraped profiles, document re-uploads and stock-tip or quote pages are skipped
(`WEAK_SOURCES`). Facts are stored per company in `connector_state` (`research:<code>`), refreshed
by the weekly SWOT run, or by the next ingestion run when a source failed.

**SWOT parameters** (`services/swot_settings.py`, Radar settings → SWOT parameters): per company,
checkboxes for the evidence sources (quarterly results, shareholding, company web pages, company news,
watched-company signals, kept daily findings) and the analysis factors (financial performance, market
position and brand, products and capacity, people and leadership, regulation and legal, competition, raw
materials and supply chain, M&A and partnerships, technology and innovation), and up to six industry news
searches for the Opportunity Analyst. Everything is ticked by default; at least one source about the
company itself and one factor are required. Stored in `connector_state` (`swot_settings:<code>`).

**Daily findings** (`agents/opportunity_analyst.py`, table `opportunity_findings`, migration 0006): the
Opportunity Analyst's opportunities and threats, shown on This week for 7 days with Keep / Dismiss;
kept ones are evidence (origin "daily") for the next weekly SWOT. The daily news comes from GNews (Tavily
news when GNews has no key) to stay within Tavily's monthly credits. Raychem RPG is not listed, so it has
no results or shareholding facts.

**LLM routes** (`agents/llm_routes.py`): Groq `openai/gpt-oss-120b` at low reasoning effort, then NVIDIA
Nemotron 3 Super, then the Azure OpenAI deployment — used for discovery, the SWOT Analyst and the
Opportunity Analyst
(thesis parsing and Ask Radar use the Azure deployment directly, with rule-based fallbacks).

**Scheduling** (`services/scheduler.py`): an in-process task runs one daily run at
`INGEST_DAILY_AT` (default 17:00): live ingestion (the news) first, then everything that searches from it,
in order, each saving what it finds — the Opportunity Analyst, the Sector Scout, discovery when
`DISCOVERY_EVERY_DAYS` (default 7) have passed, the SWOT Analyst when `SWOT_EVERY_DAYS` (default 7) have
passed (research refreshed, then every company's SWOT rebuilt), then missing sizes and the theses and
overviews made out of date. Starting the API searches nothing: a restart runs the daily run only if
today's is due and has not happened (the API was down at that time), and then once. Ingestion still goes through `IngestionWorkflow` on
Temporal when reachable (activity timeout raised to 30 minutes for paced connectors), inline otherwise.
`POST /ingest/run` and `/watchlist/discover` return 202 with a job polled at `GET /jobs/{id}`. With
several API replicas, only the one holding the `scheduler` lease (`services/lease.py`, a row in
`connector_state`) runs it, and job records are stored so any replica answers a poll.

## 16. Addendum — The radar screens (the app's main UI)

The UI is the Horizon Radar design the Corporate Strategy team worked with as a prototype, built on this
repo: `app/ui/src/radar/` (screens) and `app/radar/` (their API, mounted at `/api/v1/radar`).

| Group | Screens |
|---|---|
| Radar | **M&A Signals** — a card per signal: a watched company the RPG company could plausibly acquire (at most half its market cap or revenue, `services/company_size.py`; or a target from target discovery whose size is not verified yet), with public signals. Competitors too big to buy (Infosys for Zensar) stay in Competitor Analysis only. Each card: company, subsidiaries, listing, size against the RPG company, score, signal count and latest date, likely acquisition type with **View** (its acquisition thesis, §14, where it can be shortlisted) and **Dismiss** (to the **Archive** tab, restorable); **Competitor Analysis** — a card per watched company (listing, score, signals, latest move) with its detailed news and deal moves; **Ask Radar**; **Shortlisted signals** — the shortlisted cards, each opening its thesis; **Radar settings** — acquisition theses, SWOT parameters, watch rules, watched companies |
| Self reflection | **Self analysis** — the company's SWOT with factor tags, and the SWOT graph (impact and urgency of each opportunity and threat); **Weekly digest** — the daily Opportunity Analyst's findings of the week, with Keep / Dismiss (the weekly analyst overview and recommendations are not built yet); **The financial market** — the company's quarterly results (sales, net profit, operating margin, growth), shareholding and share price against its listed watched companies': a side-by-side table, share price indexed to 100 and operating margin by quarter, a balance sheet and market multiples table (debt to equity, interest cover, free cash flow, ROCE, 3-year sales growth, Altman Z-score with working capital estimated from working-capital days, P/E, P/B, EV/EBITDA, ROE — multiples are market facts, not a valuation, and are kept out of the agents' evidence; the balance-sheet sentence is in it), and rule-based lines on where it stands against the peer median (`services/market_data.py`, no AI). Figures are kept from the Fincrux and Alpha Vantage calls the news run already makes; the RPG companies' own are refreshed daily after the news run, and Fetch missing figures fills peers within the daily budgets (Fincrux 5, Alpha Vantage 25) |
| Workspace | This repo's Digest archive (with Generate digest) and Users and watchlist (watchlist, users, live sources, activity), rendered inside the radar shell |

**Same access model.** Every `/api/v1/radar` request needs a login and passes `radar/access.py`,
which writes an activity row (`view_radar` / `radar_change`). Every user sees every RPG company and the
group-wide "All" view, and can rebuild a SWOT or run ingestion and discovery. The persistent
"Restricted — UPSI-adjacent" strip sits on every screen.

**Real records only.** Each watched company with signals is a case (`radar/store.py`), built
from the database by `radar/bridge.py`. What users do with cases, and the theses, watch rules,
universe and activity feed they create, is snapshotted into `connector_state` (`radar/persistence.py`)
after every change and restored at boot. Screens without a real source yet — thesis matches (need sourced
acquisition targets), market performance (needs a price feed) — show an empty state that says so. A
company's SWOT shows a Build SWOT button until the agent has written one. Watch rules use the one metric with real
data, the opportunity score.
The two UIs' styles are kept apart: the radar uses its own CSS; the ZenLabs screens render inside
`.tw`, which carries Tailwind's preflight scoped by `app/ui/scripts/scope-preflight.mjs`.

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

## 4. Governance Model (designed in, not bolted on)

| Control | Implementation |
|---|---|
| Precondition, not parallel workstream | Company Secretary / Compliance sign-off on the access model and reviewer list gates ingestion **per sector** before any signal is scanned for it. |
| Named reviewer allow-list | Every reviewer is a named row in a `reviewer` table with a role (`corp_strategy_reviewer`, `compliance_admin`). No self-service signup, no "anyone with a login." |
| No shared-index integration | Horizon Radar has its own isolated data store. It is never a data source for NeuralMesh, BrandPulse, or any other submission in this set. |
| Full audit logging | Every view of a signal, entity, or digest is written to an immutable `audit_log` row: who, what, when. Compliance can query this at any time. |
| Explicit exit from AI scope | Marking a signal "Under Active Evaluation" is a one-way, audit-logged action available only to `compliance_admin`. Once set, the signal drops off the live board — the system's involvement is over. |
| Sector gating | Each subsidiary/sector carries a `compliance_gate` flag. Ingestion agents refuse to run for a sector until the flag is flipped on by an admin, modeling the CS/Compliance sign-off precondition. |

This is why Horizon Radar is a **separate submission from BrandPulse**: BrandPulse's audience is wide
and subsidiary-local (marketing reviewers); this system's audience is small, named, and centrally
controlled, often under a formal information barrier that includes marketing. Sharing a data store or
workflow between the two would create exactly the leak vector the doc calls out.

## 5. High-Level Architecture

```
                    ┌───────────────────────────────────────────────────────────┐
                    │                  SECTOR GATE (per subsidiary)             │
                    │   compliance_gate=false  →  ingestion refuses to run       │
                    └───────────────────────────────────────────────────────────┘
                                              │ gate open
                                              ▼
 ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │ News / press  │   │ Filings /    │   │ Patent       │   │ Hiring       │      Signal-ingestion
 │ connector     │   │ annual report│   │ activity     │   │ pattern      │      agents (per source
 │ (mock/pluggable)│  │ connector    │   │ connector    │   │ connector    │      type, one per sector)
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
        │            RBAC GATEWAY (named allow-list only)        │
        │   every read → audit_log(user, resource, action, ts)   │
        └───────────────────────────┬───────────────────────────┘
                                    ▼
                        ┌───────────────────────┐
                        │ Corporate Strategy UI  │  digest / signal detail /
                        │ (small, named audience)│  "mark under evaluation"
                        └───────────┬───────────┘
                                    ▼
                  Exits AI scope → RPG's existing formal,
                  restricted-list M&A process
```

## 6. Data Model

| Entity | Purpose |
|---|---|
| `subsidiary` | CEAT, KEC International, Zensar, RPG Life Sciences, Raychem RPG, Harrisons Malayalam — each with a `compliance_gate` flag and relevant sector tags. |
| `source_connector` | Registered ingestion connector (news / filings / patents / hiring), sector-scoped. |
| `raw_signal` | One ingested fact: entity, signal_type, headline, source_url, source_excerpt, observed_at. Immutable. |
| `entity` | A watched company/asset with sector/category tags used for routing. |
| `signal_cluster` | Group of `raw_signal` rows on the same entity within a rolling window — the unit the scoring agent evaluates. |
| `opportunity_score` | Composite score + rationale + contributing signal types for a cluster. |
| `routing_rule` | sector/category → subsidiary mapping (seeded from the doc's table). |
| `reviewer` | Named user: name, email, role, subsidiary scope. No open registration. |
| `digest_issue` | One weekly digest: period, items (scored clusters above threshold), recipients. |
| `audit_log` | Immutable: reviewer_id, action (`view_signal`, `view_digest`, `mark_under_evaluation`, `admin_change`), resource type/id, timestamp, IP. |

## 7. Agent Design

1. **Signal-ingestion agents** — one per source type, sector-scoped, refuse to run if `compliance_gate`
   is off. In this build they are **mocked/pluggable connectors**: a `Connector` interface with
   `fetch(entity, since) -> list[RawSignal]`, so a real news/filings/patent/hiring API integration is a
   drop-in swap, not a redesign.
2. **Distress/opportunity scoring agent** — rule-based composite: each signal type has a base weight;
   **co-occurrence within a window is scored super-linearly**, so "leadership churn + delayed filing +
   credit downgrade" scores far above three isolated headlines, matching the doc's design intent
   directly. A rationale string is generated (templated by default; an optional LLM hook can rewrite it
   in natural language — guarded behind a config flag, off by default so the demo needs no API key).
3. **Relevance-routing agent** — matches a scored cluster's entity sector/category tags against
   `routing_rule` to attach it to the right subsidiary/subsidiaries.
4. **Digest-compiler agent** — weekly job that selects clusters above the score threshold per subsidiary
   (only for gated-open subsidiaries), builds a `digest_issue`, and makes it visible only to reviewers
   scoped to that subsidiary. No autonomous outreach — the reviewer must log in to see it.

## 8. Access Control & Security Architecture

- **AuthN:** username/password against the seeded `reviewer` table only; no self-registration endpoint
  exists at all. Session token (JWT) on login.
- **AuthZ:** two roles — `corp_strategy_reviewer` (read digests/signals for their scoped subsidiaries,
  cannot manage reviewers or gates) and `compliance_admin` (everything a reviewer can do, plus manage
  the reviewer list, flip sector gates, mark a signal "under active evaluation," and query the audit
  log).
- **Audit:** middleware logs every `GET` on a signal or digest resource with the authenticated user —
  no exceptions, no opt-out.
- **Isolation:** separate database, separate deployment, no shared API surface with NeuralMesh or any
  other submission's backend. This is enforced structurally (different repo/service), not by
  configuration that could drift.
- **UPSI framing:** every restricted screen carries a persistent "Restricted — UPSI-adjacent — do not
  forward" banner, reinforcing handling expectations for reviewers.

## 9. End-to-End Flow (the CEAT cascade from the doc)

1. **Trigger** — ingestion agent detects a regional tyre-components supplier with concurrent signals:
   leadership departures, a delayed quarterly filing, a credit-rating downgrade.
2. **Scoring** — the co-occurrence bonus pushes this cluster's score well above any single-signal item.
3. **Routing** — tagged `tyres/mobility` → routed to CEAT's reviewer scope. A second, unrelated cluster
   (EPC competitor project distress) routes to KEC's scope in the same digest run.
4. **Digest** — both appear in the next weekly digest, visible only to the named reviewers scoped to
   those subsidiaries. The view is audit-logged.
5. **Hand-off** — a `compliance_admin` marks the CEAT item "Under Active Evaluation." It disappears from
   the live board; the formal M&A process takes over from here, outside this system entirely.

## 10. Implementation Architecture (this build)

Rebuilt on the **ZenLabs Agent Foundry accelerator template** (`accelerator-bootstrapper-template`) —
the same standard structure behind `digital-onboarding`, `zenarc`, `merchant-onboard`, and
`capmarkets` — so this app is consistent with how the rest of the org's agentic apps are built,
deployed, and operated: **FastAPI (async) + PostgreSQL (SQLAlchemy async + Alembic) + Redis +
Temporal (durable workflows) + OpenTelemetry/Arize Phoenix observability + Azure Key Vault**, with a
**React + Vite + Tailwind (TypeScript)** UI served by nginx, deployable to Azure Container Apps.

**Where Horizon Radar deliberately diverges from the template's own example:** the accelerator ships
a LangGraph supervisor-loop example (a chat/session "Playground") to prove the spine is wired — that
scaffold is kept in this repo, working, unmodified, as the template's own smoke test. Horizon Radar's
*own* pipeline does not use it: scoring is intentionally rule-based and auditable, never an LLM call
(§7, §14), so there is no agent/session loop for this product's actual feature set. The one piece of
platform infra Horizon Radar's own pipeline *does* use for real is **Temporal** — the signal-ingestion
pipeline runs as `IngestionWorkflow` (durable, retried on transient failure) rather than a plain
in-process function call, which is the accelerator's "Durability with Temporal" pattern applied to
what this app actually needs durability for. `POST /api/v1/ingest/run` starts that workflow, falling
back to an inline call only if Temporal/the worker isn't reachable (e.g. running the API alone without
`docker compose up`), so the demo still works with the lighter local setup.

```
rpg_horizon_radar/
├── DESIGN.md                       ← this document
├── docker-compose.local.yml        Postgres + Redis only (lightweight local dev)
├── infra/aca-setup.sh              Azure Container Apps provisioning
├── azure-pipelines-{be,fe}.yml     CI/CD — build & deploy on push to main
└── app/
    ├── main.py-equivalent → api/main.py     FastAPI app, CORS, startup seed, router registration
    ├── api/
    │   ├── auth.py                  named-reviewer JWT (replaces the template's EntraID stub —
    │   │                            see DESIGN.md §4/§8; there is no signup endpoint anywhere)
    │   ├── dependencies.py          Redis + async DB session dependencies
    │   ├── routers/                 auth, subsidiaries, entities, signals, digests, ingest,
    │   │                            reviewers, audit-log  (+ template's own health, example)
    │   └── schemas/                 Pydantic request/response models
    ├── agents/                      LangGraph supervisor scaffold — kept, unused by Horizon Radar
    ├── workflows/
    │   ├── ingestion_workflow.py    IngestionWorkflow — Horizon Radar's real Temporal usage
    │   └── activities.py            run_ingestion_activity (+ the template's example activities)
    ├── workers/worker.py            registers both ExampleWorkflow and IngestionWorkflow
    ├── db/
    │   ├── models.py                Subsidiary, Entity, RawSignal, SignalCluster,
    │   │                            OpportunityScore, ClusterSubsidiaryLink, Reviewer,
    │   │                            DigestIssue/Item, EscalationBrief, AuditLog
    │   ├── seed.py                  idempotent demo-data seed (fictional entities only)
    │   └── alembic/versions/        0001 (template baseline) + 0002 (Horizon Radar schema)
    ├── ingestion/connectors/        base.py + mock_news/mock_filings/mock_patents/mock_hiring
    ├── services/
    │   ├── scoring.py                co-occurrence-weighted scoring + rationale (no LLM)
    │   ├── routing.py                sector/category → subsidiary
    │   ├── visibility.py             gate + reviewer-scope visibility rule
    │   ├── ingest.py                 shared by seed.py, the Temporal activity, and the inline fallback
    │   ├── digest.py                 weekly digest compiler
    │   ├── escalation_brief.py       §14 hand-off packet generator
    │   └── audit.py                  audit log writer
    └── ui/src/
        ├── pages/                    Login, Dashboard, SignalDetail, DigestArchive, Admin
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

Deployment note: for the actual pilot this should run in RPG's restricted network segment with access
scoped to Corporate Strategy + Compliance only, consistent with the "small, named, centrally-controlled
audience" requirement — not on shared/public infrastructure. `infra/aca-setup.sh` and the Azure
Pipelines are the template's standard path to Azure Container Apps; using them for a real pilot still
requires the network/access scoping above, which is outside what the pipeline itself enforces.

## 11. MVP / Phase 1 — Delivery Plan (as specified in the submission)

1. **Precondition:** Company Secretary / Compliance sign-off on the access model and reviewer list —
   modeled here as the `compliance_gate` flag, defaulted **off** for every subsidiary except the pilot.
2. **Pilot sector:** CEAT (tyres/mobility) only — gate defaulted **on** for CEAT in seed data, off for
   the rest, so the running app itself demonstrates the phased-rollout posture rather than just
   claiming it.
3. **Validate:** scoring agent tested against the doc's own example cascade (regional tyre-components
   supplier + KEC EPC competitor) via seeded mock signals.
4. **Feedback loop:** one pilot weekly digest to the named Corporate Strategy group before expanding
   sector gates.

## 12. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Reviewer list creep ("just add me") | Reviewer CRUD is `compliance_admin`-only and every change is audit-logged. |
| Signal reaching the wrong subsidiary | Routing is explicit table-driven (`routing_rule`), not inferred per-request — auditable and correctable without touching scoring logic. |
| Tool drifting into a decisioning role | "Mark Under Active Evaluation" is one-way and removes the item from the live system — there is no path back to "just a flag" once escalated, by design. |
| Real connectors introducing unvetted data before sign-off | Sector gate blocks ingestion, not just display — no data for a closed sector is ever fetched or stored. |

## 13. Success Metrics (for the pilot)

- Time-to-detection for a known past distress/opportunity event, measured against when it became
  public knowledge (target: materially earlier, matching the doc's "weeks before either became public
  knowledge" framing).
- Reviewer-rated signal relevance (kept/escalated vs. dismissed) during the CEAT pilot.
- Zero unaudited views — 100% of signal/digest reads have a matching `audit_log` row.

## 14. Addendum — Escalation Brief (the hand-off packet)

Corporate Strategy asked for "pros and cons, economics" to carry into the formal process at the moment
a signal is escalated. This is added as a bounded feature at the **existing hand-off point** (step 5 of
the cascade in §9) — it does not move the scoring/ingestion pipeline's non-goals in §3. The hard line:
**this brief is qualitative and directional. It never computes or displays a valuation, price, multiple,
or synergy dollar figure**, because the system has no real financial data on any target and fabricating
numbers here would be actively misleading to the people using it to decide whether to pursue a deal.

**Trigger:** generated once, automatically, in the same transaction as `mark-under-evaluation` — not
before (a live signal shouldn't carry a "should we do this deal" narrative) and not editable after (it's
a timestamped snapshot of what the system knew at the moment of hand-off, consistent with "the agent's
job stops at flagging").

**Contents (all templated from data already in the system — no new data source, no LLM call required):**

| Section | Derived from | Example |
|---|---|---|
| Header | cluster + entity + score + escalation metadata | entity, subsidiary(ies), score, flagged-at, escalated-by/at |
| Signal summary | the cluster's existing `raw_signal` rows | reused as-is — nothing new to build |
| Strategic pros | rule templates keyed to which signal_types are present + sector overlap | credit_downgrade/delayed_filing present → "possible distress-driven opening, target may be more receptive to conversations"; patent_shift present → "signals a capability gap the target may be exiting"; always → "surfaced via public sources ahead of broad market awareness" |
| Strategic cons / risks | rule templates, inverse-weighted by signal-type count (fewer distinct types → stronger caution) | always → "unconfirmed by primary diligence — signals are public-pattern inference, not verified financials"; sector-overlap with an RPG subsidiary → "check regulatory/anti-trust overlap before any approach"; low signal-type count → "single/dual-signal flags carry a materially higher false-positive rate than multi-signal ones" |
| Directional considerations *(explicitly labeled "illustrative, not a valuation")* | a small heuristic checklist, not a computed number | Deal complexity: Low/Medium/High (from sector/category breadth); Revenue-synergy potential: heuristic Y/N (sector overlap with the routed subsidiary); Cost-synergy potential: heuristic Y/N (same-sector overlap); Suggested first formal-process step: fixed text pointing at Corporate Development's standard diligence intake |
| Disclaimer footer (fixed, non-optional) | — | *"Generated from public-signal pattern-matching only. Contains no financial valuation and no confirmed non-public information. Not a recommendation to proceed — a set of directional prompts for the formal M&A process."* |

**Data model addition:** `EscalationBrief` (1:1 with `signal_cluster`) — id, cluster_id, generated_at,
escalated_by_id, pros (list), cons (list), directional_considerations (list of {label, value}),
deal_complexity (Low/Medium/High), disclaimer (fixed text, stored for point-in-time audit fidelity even
if the constant wording changes later).

**API addition:** `mark-under-evaluation` now also creates the brief in the same transaction; a new
`GET /api/v1/signals/{id}/escalation-brief` returns it (same visibility rule as the underlying signal,
audit action `view_escalation_brief`). No update/regenerate endpoint — it's write-once.

**UI addition:** once a signal's status is `under_evaluation`, `SignalDetail` shows an "Escalation
Brief" section (pros / cons / directional considerations / disclaimer, visually distinct as a
hand-off document) with a plain-text export for pasting into the formal process's own paperwork.

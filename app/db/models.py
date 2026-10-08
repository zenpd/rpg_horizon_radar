"""ORM models.

``Session`` is the accelerator baseline's chat-session table. Nothing in
Horizon Radar uses it; it stays only because migration 0001 created it.

Everything below it is RPG Horizon Radar's own domain model. See
``DESIGN.md`` at the repo root for the full data-model rationale. Two
invariants worth restating here because they're safety-relevant, not just
structural:

- The six RPG subsidiaries (``Subsidiary``) are ONLY the internal routing
  targets / audience of this tool — never watched or "distressed" entities
  themselves.
- A watched ``Entity`` is a real, publicly listed company that the live
  connectors track (``origin="discovered"`` or ``"manual"``), from the moment
  it is found or added (``status="watching"``) until someone removes it
  (``"dismissed"``). There is no approval step (migration 0005). Earlier
  versions also seeded fictional demo companies; migration 0004 removed them.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    current_step: Mapped[str] = mapped_column(String(64), default="start")
    # Full agent-graph state, persisted for resume + audit.
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ═════════════════════════════════════════════════════════════════════════════
# RPG Horizon Radar domain models
# ═════════════════════════════════════════════════════════════════════════════


class Subsidiary(Base):
    """One of the six RPG operating subsidiaries — a routing target only."""

    __tablename__ = "subsidiaries"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. "CEAT"
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sectors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    signal_focus: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Entity(Base):
    """A WATCHED company: a real listed one. See the module docstring.

    origin: discovered | manual
    status: watching | dismissed — only ``watching`` entities are ingested. A
        dismissed company is never re-added by discovery.
    """

    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint("status in ('watching', 'dismissed')", name="ck_entity_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sectors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)  # used for routing
    category: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="manual", server_default="manual")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="watching", server_default="watching")
    # competitor (watchlist discovery, or added by hand) | target (target discovery): only a target small
    # enough for the RPG company to buy becomes an M&A signal (services/company_size.py)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="competitor", server_default="competitor")
    # How headlines and APIs name the company ("Apollo Tyres" for "Apollo Tyres Ltd"); blank = derived from name.
    query_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    nse_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Discovery evidence: {for: subsidiary code, kind, why, sources: [{title, url}], found_at, last_seen_at, model}
    discovery: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    watched_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # raw_signals is queried directly (never traversed via this attribute), so
    # it's left at the default lazy strategy. clusters IS traversed as an
    # attribute (routers/entities.py) so it must be eager under AsyncSession —
    # implicit lazy-loading isn't supported there without a running greenlet.
    raw_signals: Mapped[list["RawSignal"]] = relationship(back_populates="entity", cascade="all, delete-orphan")
    clusters: Mapped[list["SignalCluster"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", lazy="selectin"
    )


class RawSignal(Base):
    """One ingested public fact about a watched entity. Immutable once written.

    signal_type: leadership_churn | delayed_filing | credit_downgrade |
        patent_shift | hiring_scaledown | hiring_scaleup | press_distress |
        press_opportunity
    source_type: news | filing | patent | hiring | employee
    provider: the live connector that fetched it ("NSE", "GNews" ...).
    """

    __tablename__ = "raw_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    headline: Mapped[str] = mapped_column(String(512), nullable=False)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="mock", server_default="mock")
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    entity: Mapped["Entity"] = relationship(back_populates="raw_signals")


class SignalCluster(Base):
    """Group of RawSignal rows on the same entity within a rolling window —
    the unit the scoring agent evaluates."""

    __tablename__ = "signal_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False, index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="live")  # live | under_evaluation
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    evaluated_by_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # All of these are traversed as plain attributes across the routers
    # (cluster.entity.name, cluster.opportunity_score.score, …) rather than
    # via an explicit eager-load query option, so each must be `selectin`
    # under AsyncSession — implicit lazy-loading needs a sync greenlet that
    # isn't available there.
    entity: Mapped["Entity"] = relationship(back_populates="clusters", lazy="selectin")
    opportunity_score: Mapped["OpportunityScore | None"] = relationship(
        back_populates="cluster", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    subsidiary_links: Mapped[list["ClusterSubsidiaryLink"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan", lazy="selectin"
    )
    escalation_brief: Mapped["EscalationBrief | None"] = relationship(
        back_populates="cluster", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    evaluated_by: Mapped["Reviewer | None"] = relationship(foreign_keys=[evaluated_by_id], lazy="selectin")


class OpportunityScore(Base):
    """Composite distress/opportunity score for a SignalCluster (one-to-one).
    See ``services/scoring.py`` for the auditable, rule-based algorithm —
    deliberately no external LLM call."""

    __tablename__ = "opportunity_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("signal_clusters.id"), nullable=False, unique=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 0-100
    signal_types_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    cluster: Mapped["SignalCluster"] = relationship(back_populates="opportunity_score")


class ClusterSubsidiaryLink(Base):
    """Many-to-many routing result: which subsidiaries a SignalCluster was
    routed to, by sector overlap (``services/routing.py``)."""

    __tablename__ = "cluster_subsidiary_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("signal_clusters.id"), nullable=False, index=True)
    subsidiary_code: Mapped[str] = mapped_column(ForeignKey("subsidiaries.code"), nullable=False, index=True)

    # Traversed as link.cluster in services/digest.py.
    cluster: Mapped["SignalCluster"] = relationship(back_populates="subsidiary_links", lazy="selectin")
    subsidiary: Mapped["Subsidiary"] = relationship()


class Reviewer(Base):
    """A user who can sign in. Users have no roles: every user sees everything
    and can add or remove other users. No self-service signup exists — see
    ``api/auth.py``. (The table keeps its original name.)"""

    __tablename__ = "reviewers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class DigestIssue(Base):
    """One weekly digest compilation."""

    __tablename__ = "digest_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)

    # Traversed as digest.items in routers/digests.py.
    items: Mapped[list["DigestItem"]] = relationship(
        back_populates="digest", cascade="all, delete-orphan", lazy="selectin"
    )
    created_by: Mapped["Reviewer | None"] = relationship()


class DigestItem(Base):
    """Snapshot row of a scored cluster included in a digest, per subsidiary."""

    __tablename__ = "digest_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_id: Mapped[int] = mapped_column(ForeignKey("digest_issues.id"), nullable=False, index=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("signal_clusters.id"), nullable=False, index=True)
    subsidiary_code: Mapped[str] = mapped_column(ForeignKey("subsidiaries.code"), nullable=False, index=True)

    digest: Mapped["DigestIssue"] = relationship(back_populates="items")
    # Traversed as item.cluster in routers/digests.py.
    cluster: Mapped["SignalCluster"] = relationship(lazy="selectin")
    subsidiary: Mapped["Subsidiary"] = relationship()


class EscalationBrief(Base):
    """Qualitative, directional hand-off packet generated once, at the moment
    a SignalCluster is marked under_evaluation. See DESIGN.md §14.

    HARD RULE, enforced in ``services/escalation_brief.py``: this must never
    store a computed valuation, price, multiple, or synergy dollar figure —
    the system has no real financial data on any watched entity."""

    __tablename__ = "escalation_briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("signal_clusters.id"), nullable=False, unique=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    escalated_by_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)

    pros: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    directional_considerations: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    deal_complexity: Mapped[str] = mapped_column(String(16), nullable=False)  # Low | Medium | High
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)

    cluster: Mapped["SignalCluster"] = relationship(back_populates="escalation_brief")
    # Traversed as brief.escalated_by.name in routers/signals.py.
    escalated_by: Mapped["Reviewer | None"] = relationship(lazy="selectin")


class AuditLog(Base):
    """Activity history: who did what, when. Every user can read it; no
    endpoint deletes rows from it. See ``services/audit.py``.

    action: view_signal_list | view_signal | view_escalation_brief |
        view_digest | mark_under_evaluation | user_change | watchlist_change |
        ingest_run | watchlist_discovery | view_radar | radar_change
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)
    reviewer_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ConnectorState(Base):
    """Small key/value store for the live connectors and the scheduler: last
    pull per source and entity, daily call budgets, rating/posting snapshots
    that later readings are compared against, resolved stock symbols."""

    __tablename__ = "connector_state"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class SwotBrief(Base):
    """A SWOT the radar's SWOT Analyst agent built for one subsidiary (agents/swot_analyst.py),
    one row per rebuild; the newest row is current and is loaded back into the radar at
    startup (radar/bridge.py). Every item cites its evidence. Never feeds scoring
    (services/scoring.py stays rule-based)."""

    __tablename__ = "swot_briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    subsidiary_code: Mapped[str] = mapped_column(ForeignKey("subsidiaries.code"), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    generated_by_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)  # None = scheduler
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    rounds: Mapped[int] = mapped_column(nullable=False, default=1)
    # {swot, positions, detail, source}: the SWOT and TOWS moves, impact/urgency per item, each
    # item's reasoning and cited sources, and how it was built (model, rounds, evidence mix)
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)

    generated_by: Mapped["Reviewer | None"] = relationship(lazy="selectin")


class OpportunityFinding(Base):
    """One opportunity or threat the Opportunity Analyst found in a day's news for one subsidiary
    (agents/opportunity_analyst.py), with how it affects that subsidiary's SWOT. A user keeps or
    dismisses it; kept findings of the last week are evidence for the next weekly SWOT.

    kind: opportunity | threat
    status: new | kept | dismissed
    """

    __tablename__ = "opportunity_findings"
    __table_args__ = (
        CheckConstraint("kind in ('opportunity', 'threat')", name="ck_finding_kind"),
        CheckConstraint("status in ('new', 'kept', 'dismissed')", name="ck_finding_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subsidiary_code: Mapped[str] = mapped_column(ForeignKey("subsidiaries.code"), nullable=False, index=True)
    found_on: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The SWOT item it affects (S1, W2 ... as the SWOT stood that day), or None for something new.
    swot_ref: Mapped[str | None] = mapped_column(String(8), nullable=True)
    swot_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    effect: Mapped[str] = mapped_column(Text, nullable=False, default="")
    action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    impact: Mapped[int] = mapped_column(nullable=False, default=0)
    urgency: Mapped[int] = mapped_column(nullable=False, default=0)
    # [{text, source, date, url}] — the news items it cites
    evidence: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new", server_default="new")
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChatThread(Base):
    """One Ask Radar conversation. Private to the user who started it: every read and write is
    filtered on ``reviewer_id`` (radar/api.py), so no other user can list or open it."""

    __tablename__ = "chat_threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("reviewers.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(64), nullable=False, default="All")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class ChatMessage(Base):
    """One turn in an Ask Radar conversation.

    role: user | assistant
    sources: the numbered evidence the answer cites — [{id, kind: radar | web, text, source, date, url}]
    """

    __tablename__ = "chat_messages"
    __table_args__ = (CheckConstraint("role in ('user', 'assistant')", name="ck_chat_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(String(64), nullable=False, default="All")
    sources: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    used_web: Mapped[bool] = mapped_column(nullable=False, default=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

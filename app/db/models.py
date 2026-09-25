"""ORM models.

``Session`` is the accelerator baseline (kept working — it backs the example
Playground router's optional DB-persistence activity).

Everything below it is RPG Horizon Radar's own domain model. See
``DESIGN.md`` at the repo root for the full data-model rationale. Two
invariants worth restating here because they're safety-relevant, not just
structural:

- The six RPG subsidiaries (``Subsidiary``) are ONLY the internal routing
  targets / audience of this tool — never watched or "distressed" entities
  themselves.
- Every ``Entity`` (a watched company) MUST be fully fictional/synthetic —
  enforced both by a server-side default and a DB CHECK constraint. This
  table must never hold a real, identifiable company name as the subject of
  a distress/acquisition-target signal.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
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
    compliance_gate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signal_focus: Mapped[str] = mapped_column(Text, nullable=False, default="")


class Entity(Base):
    """A WATCHED company — always fully fictional/synthetic. See module
    docstring and ``db/seed.py`` for the synthetic-data policy."""

    __tablename__ = "entities"
    __table_args__ = (CheckConstraint("is_fictional = true", name="ck_entity_must_be_fictional"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sectors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)  # used for routing
    category: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_fictional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # raw_signals is queried directly (never traversed via this attribute), so
    # it's left at the default lazy strategy. clusters IS traversed as an
    # attribute (routers/entities.py) so it must be eager under AsyncSession —
    # implicit lazy-loading isn't supported there without a running greenlet.
    raw_signals: Mapped[list["RawSignal"]] = relationship(back_populates="entity", cascade="all, delete-orphan")
    clusters: Mapped[list["SignalCluster"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan", lazy="selectin"
    )


class RawSignal(Base):
    """One ingested (mocked) fact about a watched entity. Immutable once written.

    signal_type: leadership_churn | delayed_filing | credit_downgrade |
        patent_shift | hiring_scaledown | hiring_scaleup | press_distress |
        press_opportunity
    source_type: news | filing | patent | hiring
    """

    __tablename__ = "raw_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    headline: Mapped[str] = mapped_column(String(512), nullable=False)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
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
    routed to. Recorded even for gated-off subsidiaries — visibility is
    filtered at read time (see ``services/visibility.py``), not at write time."""

    __tablename__ = "cluster_subsidiary_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("signal_clusters.id"), nullable=False, index=True)
    subsidiary_code: Mapped[str] = mapped_column(ForeignKey("subsidiaries.code"), nullable=False, index=True)

    # Traversed as link.cluster in services/digest.py.
    cluster: Mapped["SignalCluster"] = relationship(back_populates="subsidiary_links", lazy="selectin")
    subsidiary: Mapped["Subsidiary"] = relationship()


class Reviewer(Base):
    """Named reviewer allow-list row. No self-service signup exists anywhere
    in this app — see ``api/auth.py``.

    role: corp_strategy_reviewer | compliance_admin
    """

    __tablename__ = "reviewers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    subsidiary_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
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
    """Immutable audit trail. No endpoint anywhere may delete rows from this
    table. See ``services/audit.py``.

    action: view_signal_list | view_signal | view_escalation_brief |
        view_digest | mark_under_evaluation | admin_change | gate_change |
        ingest_run
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

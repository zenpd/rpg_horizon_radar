// Shared API types for RPG Horizon Radar, matching the FastAPI schemas under
// app/api/schemas/*.py (see services/api.ts for the endpoints that return
// them). Kept as plain interfaces — this is a demo app, not a library.

export interface User {
  id: number;
  name: string;
  email: string;
  role: "compliance_admin" | "corp_strategy_reviewer";
  subsidiary_scopes: string[];
}

export interface TokenResponse {
  token: string;
  user: User;
}

// ---- Subsidiaries ----
export interface Subsidiary {
  code: string;
  name: string;
  sectors: string[];
  compliance_gate: boolean;
  signal_focus: string;
}

// ---- Entities ----
export interface EntityOut {
  id: number;
  name: string;
  sectors: string[];
  category: string;
}

// ---- Signals ----
export type SignalStatus = "live" | "under_evaluation";

export interface RawSignalOut {
  id: number;
  signal_type: string;
  source_type: string;
  headline: string;
  source_excerpt: string;
  source_url: string;
  provider: string; // "NSE", "GNews" ... or "mock" for the fictional demo connectors
  observed_at: string;
}

export interface SignalClusterSummary {
  id: number;
  entity_name: string;
  entity_sectors: string[];
  subsidiaries: string[];
  score: number;
  rationale: string;
  signal_types: string[];
  status: SignalStatus | string;
  updated_at: string;
}

// The real API flattens entity fields onto the cluster (entity_name /
// entity_sectors come from SignalClusterSummary, entity_category is added
// here) rather than nesting a separate `entity` object.
export interface SignalClusterDetail extends SignalClusterSummary {
  entity_id: number;
  entity_category: string;
  window_start: string;
  window_end: string;
  raw_signals: RawSignalOut[];
  evaluated_by?: string | null;
  evaluated_at?: string | null;
}

// ---- Escalation brief ----
export interface DirectionalConsideration {
  label: string;
  value: string;
}

export interface EscalationBrief {
  id: number;
  cluster_id: number;
  generated_at: string;
  escalated_by?: string | null;
  pros: string[];
  cons: string[];
  directional_considerations: DirectionalConsideration[];
  deal_complexity: string;
  disclaimer: string;
}

// ---- Digests ----
export interface DigestSummary {
  id: number;
  period_start: string;
  period_end: string;
  created_at: string;
  subsidiary_breakdown: Record<string, number>;
}

export interface DigestItem {
  subsidiary_code: string;
  cluster: SignalClusterSummary;
}

export interface DigestDetail {
  id: number;
  period_start: string;
  period_end: string;
  created_at: string;
  items: DigestItem[];
}

// ---- Ingest + background jobs ----
export interface IngestRunResult {
  new_raw_signals: number;
  clusters_updated: number;
  errors: string[];
  changed_subsidiaries: string[];
  via: string;
  swot_rebuilt: string[];
  swot_errors: string[];
}

export interface Job<R = Record<string, unknown>> {
  id: string;
  kind: string;
  status: "running" | "completed" | "failed";
  result: R | null;
  error: string | null;
  started_by: string;
  started_at: string;
  finished_at: string | null;
}

// ---- Watchlist (real companies) ----
export interface DiscoverySource {
  title: string;
  url: string;
}

export interface WatchlistEntity {
  id: number;
  name: string;
  sectors: string[];
  category: string;
  is_fictional: boolean;
  origin: "seed" | "discovered" | "manual";
  status: "watching" | "proposed" | "dismissed";
  query_name: string;
  nse_symbol: string | null;
  discovery: {
    for?: string;
    kind?: string;
    why?: string;
    sources?: DiscoverySource[];
    found_at?: string;
    last_seen_at?: string;
    model?: string;
  } | null;
  approved_by: string | null;
  approved_at: string | null;
  raw_signal_count: number;
  score: number | null;
}

export interface ConnectorStatus {
  name: string;
  source_type: string;
  configured: boolean;
  min_days: number;
  entities_pulled: number;
  last_pull: string | null;
  budget: { date: string; used: number } | null;
}

export interface SchedulerStatus {
  enabled: boolean;
  ingest_daily_at: string;
  discovery_every_days: number;
  auto_swot: boolean;
  last: { ingest: string | null; discovery: string | null };
  next: { ingest: string; discovery: string };
  running: string | null;
  last_error: string | null;
}

export interface SourcesStatus {
  connectors: ConnectorStatus[];
  llm_routes: string[];
  last_run: { at: string; errors: string[]; new_raw_signals?: number } | null;
  scheduler: SchedulerStatus;
}

// ---- SWOT briefs ----
export interface SwotItem {
  text: string;
  evidence: string[];
  reasoning: string;
  entity?: string | null;
  impact?: number;
  urgency?: number;
}

export interface SwotEvidence {
  id: string;
  kind: "signal" | "team_note";
  headline: string;
  entity?: string;
  fictional?: boolean;
  signal_type?: string;
  provider?: string;
  excerpt?: string;
  url?: string | null;
  observed_at?: string;
  quadrant?: string;
}

export interface SwotBrief {
  id: number;
  subsidiary_code: string;
  generated_at: string;
  generated_by: string;
  model: string;
  rounds: number;
  content: {
    summary: string;
    strengths: SwotItem[];
    weaknesses: SwotItem[];
    opportunities: SwotItem[];
    threats: SwotItem[];
  };
  evidence: SwotEvidence[];
}

export interface TeamNotes {
  strengths: string[];
  weaknesses: string[];
}

// ---- Reviewers ----
export interface Reviewer {
  id: number;
  name: string;
  email: string;
  role: "compliance_admin" | "corp_strategy_reviewer";
  subsidiary_scopes: string[];
  created_at: string;
}

export interface ReviewerCreate {
  name: string;
  email: string;
  password: string;
  role: "compliance_admin" | "corp_strategy_reviewer";
  subsidiary_scopes: string[];
}

// ---- Audit log ----
export interface AuditLogEntry {
  id: number;
  reviewer_id: number | null;
  reviewer_name_snapshot: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  detail: string | null;
  created_at: string;
}

// Shared API types for RPG Horizon Radar, matching the FastAPI schemas under
// app/api/schemas/*.py (see services/api.ts for the endpoints that return
// them). Kept as plain interfaces.

export interface User {
  id: number;
  name: string;
  email: string;
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
  provider: string; // the live connector that fetched it: "NSE", "GNews" ...
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
  origin: "discovered" | "manual";
  status: "watching" | "dismissed";
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
  watched_since: string | null;
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
  opportunity_daily_at: string;
  swot_every_days: number;
  last: { ingest: string | null; discovery: string | null; opportunities: string | null; swot: string | null };
  next: { ingest: string; discovery: string; opportunities: string; swot: string };
  running: string | null;
  last_error: string | null;
}

export interface SourcesStatus {
  connectors: ConnectorStatus[];
  llm_routes: string[];
  last_run: { at: string; errors: string[]; new_raw_signals?: number } | null;
  scheduler: SchedulerStatus;
}

// ---- Reviewers ----
export interface Reviewer {
  id: number;
  name: string;
  email: string;
  created_at: string;
}

export interface ReviewerCreate {
  name: string;
  email: string;
  password: string;
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

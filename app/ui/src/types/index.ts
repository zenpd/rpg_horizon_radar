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

// ---- Ingest ----
export interface IngestRunResult {
  new_raw_signals: number;
  clusters_updated: number;
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

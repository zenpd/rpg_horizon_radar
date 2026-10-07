// Thin client for the radar screens' API (/api/v1/radar, backend app/radar/api.py).
/* eslint-disable @typescript-eslint/no-explicit-any */

import { TOKEN_KEY } from "../services/api";

export interface Me { name: string; companies: string[] }

export type SignalStatus = "open" | "shortlisted" | "dismissed";
export interface SizeFit { ok: boolean | null; ratio: number | null; metric: "market_cap" | "revenue" | null; label: string }

/** An M&A signal: a watched company with public signals, which users view (its acquisition thesis),
 * shortlist, or dismiss to the archive. */
export interface CaseSummary {
  score_detail?: ScoreDetail | null;
  id: string;
  kind: "rival";
  who: string;
  title: string;
  company: string;
  companies: string[];
  status: SignalStatus;
  status_label: string;
  status_at: string | null;
  date: string;
  score: number | null;
  chips: string[];
  signal_count: number;
  listing: string | null;
  role: "competitor" | "target";
  /** How big it is against the RPG company (services/company_size.fit); signal: it is an M&A signal for it. */
  size: SizeFit & { signal: boolean };
  /** Each tag's latest signal, with its link. */
  chip_links: Record<string, Signal>;
  recommended: { type: string; title: string; co: string } | null;
}

export interface Signal { date: string; label: string; text: string; source: string; url: string | null }

export interface ScoreInfo { score: number; rationale: string | null; types: string[] }

export interface QuickLook { signals: Signal[]; score: ScoreInfo | null }

export interface CaseDetail extends CaseSummary { quick: QuickLook }

export interface RecCard {
  co: string;
  type: "SO" | "WO" | "ST" | "WT";
  title: string;
  uses: string[];
  uses_text: Record<string, string>;
  case_id: string;
  why: string;
  tows: [string, string];
  case: CaseDetail;
}

export interface SwotSource { id: string; text: string; source: string; date: string | null; url: string | null; origin: "live" | "self" | "daily"; origin_label: string }
export interface SwotItem { id: string; text: string; case_id?: string | null; reasoning: string | null; factor?: string | null; sources: SwotSource[] }
export interface SwotMethod { built_by: "agent"; summary: string; steps: string[]; model?: string; at?: string; rounds?: number; live_signals_available: number }
export interface SwotView { company: string; S: SwotItem[]; W: SwotItem[]; O: SwotItem[]; T: SwotItem[]; moves: number; set_aside: number; source: { by: "agent"; model?: string; at?: string; research_at?: string | null }; method: SwotMethod }
export interface Position { id: string; q: "O" | "T"; text: string; case_id: string | null; impact: number; urgency: number; used: boolean; move: string | null }

export interface Home {
  scope: string;
  week: string;
  analyst: string;
  recommended: RecCard[];
  set_aside: { co: string; case_id: string; why: string; who: string }[];
  watched: CaseDetail[];
  swot: SwotView | null;
  swot_status: { built: boolean; message: string | null } | null;
  positions: Position[] | null;
  tiles: { company: string; swot: SwotView | null; watched: number; signals: number }[] | null;
  signals: (Signal & { who: string; case_id: string })[];
  signal_count: number;
}

export interface SwotJob { id: string; company: string; status: "running" | "completed" | "failed"; phase: "research" | "drafting"; round: number; max_rounds: number; error: string | null }

export interface WatchedCompany { name: string; status: "watching"; why: string; sources: { title: string; url: string }[]; origin: string; stock_symbol: string | null; signals: number; found_at: string | null }

export interface SignalsStatus {
  sources: { name: string; configured: boolean; note?: string }[];
  companies: { company: string; live_signals: number; companies: WatchedCompany[] }[];
  last_refresh: string | null;
  errors: string[];
}

export interface SchedulerStatus {
  enabled: boolean; signals_at: string; rivals_every_days: number; opportunities_at: string; swot_every_days: number; running: string | null; last_error: string | null;
  last: { rivals: string | null; signals: string | null; opportunities: string | null; swot: string | null };
  next: { rivals: string; signals: string; opportunities: string; swot: string } | null;
}

export interface SignalJob { id: string; status: "running" | "completed" | "failed"; result: { companies: string[]; signals: number; errors: string[] } | null; error: string | null }

export interface SwotParams { company: string; sources: string[]; factors: string[]; sector_queries: string[] }
export interface SwotParamsAll { sources: { key: string; label: string }[]; factors: { key: string; label: string }[]; companies: SwotParams[] }

/** One opportunity or threat the daily Opportunity Analyst found, judged against the company's SWOT. */
export interface Finding {
  id: number; company: string; date: string; found_on: string; kind: "opportunity" | "threat"; title: string; summary: string;
  swot_ref: string | null; swot_text: string; effect: string; action: string; impact: number; urgency: number;
  sources: { text: string; source: string; date: string; url: string | null }[]; status: "new" | "kept" | "dismissed"; model: string;
}
export interface Findings { company: string; findings: Finding[]; last_run: string | null; news_read: number | null; errors: string[] }

/** The Acquisition Thesis agent's thesis for one M&A signal and one RPG company. */
export interface ThesisItem { text: string; evidence: string[] }
export interface PostSwotItem { text: string; change: "new" | "strengthened" | "weakened" | "carried over"; swot_ref: string | null; evidence: string[] }
export interface Connection { name: string; relation: string; detail: string; evidence: string[]; link: "RPG company" | "watched company" | null }
export interface ThesisDoc {
  case_id: string; company: string; target: string; at: string; model: string; rounds: number; research_errors: string[]; swot_at: string | null;
  evidence: { id: string; date: string; source: string; text: string; url: string | null }[];
  draft: {
    headline: string; acquisition_type: "full" | "partial" | "unclear"; acquisition_reason: string;
    background: { summary: string; points: ThesisItem[] };
    connections: Connection[];
    target_swot: { strengths: ThesisItem[]; weaknesses: ThesisItem[]; opportunities: ThesisItem[]; threats: ThesisItem[] };
    comparison: { point: string; effect: "complements" | "overlaps" | "conflicts"; swot_ref: string | null; evidence: string[] }[];
    /** Absent on theses written before it was added; they get it at their weekly rewrite. */
    post_swot?: Record<"strengths" | "weaknesses" | "opportunities" | "threats", PostSwotItem[]>;
    fitment: { dimension: string; rating: "strong" | "moderate" | "weak" | "unknown"; reasoning: string; evidence: string[] }[];
    ripple: { company: string; effect: "opportunity" | "neutral" | "risk"; reasoning: string }[];
    open_questions: string[];
  };
}
export interface SignalCard extends CaseSummary { thesis: { headline: string; acquisition_type: string; at: string } | null }
export interface SignalList { company: string; status: SignalStatus; signals: SignalCard[]; counts: Record<SignalStatus, number> }

/** How the rule-based opportunity score is built (services/scoring.py). */
export interface ScoreDetail {
  parts: { type: string; weight: number }[]; base: number; kinds: number; multiplier: number; raw: number; score: number;
  max: number; window_days: number; multipliers: Record<string, number>;
}
export interface Rival {
  score_detail: ScoreDetail | null; entity_id: number; name: string; status: "watching"; score: number | null; signals: number; latest_move: string | null; latest_date: string | null;
  why: string | null; sources: { title: string; url: string }[]; case_id: string | null; timeline: Signal[];
  nse_symbol: string | null; origin: string | null; found_at: string | null; signal_status: SignalStatus | null;
  role: "competitor" | "target"; size: SizeFit;
}

/** Competitor Analysis → Overview: recent moves and financials as stored, and the Competitor Profile agent's analysis. */
export interface ProfileDoc {
  name: string; company: string; at: string; model: string; rounds: number; research_errors: string[];
  evidence: { id: string; date: string; source: string; text: string; url: string | null }[];
  draft: {
    summary: string;
    swot: Record<"strengths" | "weaknesses" | "opportunities" | "threats", ThesisItem[]>;
    versus: { point: string; side: "ahead" | "behind" | "head-to-head"; swot_ref: string | null; evidence: string[] }[];
    threat: { level: "high" | "medium" | "low"; reason: string };
    watch: string[];
  };
}
export interface Overview {
  company: string; rival: Rival; moves: { group: string; signals: Signal[] }[];
  financials: { text: string; source: string; date: string; url: string | null }[]; researched_at: string | null;
  profile: ProfileDoc | null; failed: { error: string; at: string } | null;
}

/** Self reflection → The financial market (services/market_data.py). */
export interface MarketRow {
  name: string; own: boolean; role: string; nse_symbol: string | null; entity_id: number | null; market_cap: number | null;
  has_results?: boolean; has_prices?: boolean; quarter?: string | null; ttm_sales?: number | null; ttm_profit?: number | null;
  sales_yoy?: number | null; profit_yoy?: number | null; opm?: number | null; opm_series?: number[]; quarters?: string[];
  promoters?: number | null; fiis?: number | null; close?: number; close_date?: string; chg_30?: number | null; chg_period?: number | null;
  prices?: [string, number][];
}
export interface Market {
  company: string; listed: boolean; nse_symbol: string | null; own: MarketRow; peers: MarketRow[];
  standing: { measure: string; verdict: "ahead" | "behind" | "level" | "info"; text: string }[];
  pending: string[]; unlisted: string[]; budget: Record<string, { date: string; used: number }>;
}

export interface Deal extends Signal { company: string; type: string; case_id: string; for: string }

export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

// The radar API sits behind the login: send the same token the rest of the app
// uses (services/api.ts), and go back to the login page when it is missing or expired.
async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers: Record<string, string> = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(`/api/v1/radar${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (r.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    window.location.assign("/login");
    throw new ApiError(401, "Your session has ended. Please sign in again.");
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, (data && (data.detail || data.title)) || `Request failed (${r.status})`);
  return data as T;
}

const q = (o: Record<string, string | undefined>) =>
  "?" + Object.entries(o).filter(([, v]) => v !== undefined).map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`).join("&");

export const api = {
  me: () => call<Me>("GET", "/me"),
  reference: () => call<{ sector_labels: Record<string, string> }>("GET", "/reference"),
  home: (company: string) => call<Home>("GET", "/home" + q({ company })),
  rebuildSwot: (company: string, research = false) => call<SwotJob>("POST", `/swot/${encodeURIComponent(company)}/rebuild` + (research ? "?research=true" : "")),
  swotJob: (id: string) => call<SwotJob>("GET", `/swot-jobs/${id}`),
  signalsStatus: () => call<SignalsStatus>("GET", "/signals/status"),
  scheduler: () => call<SchedulerStatus>("GET", "/scheduler"),
  findRivals: () => call<SignalJob>("POST", "/rivals/discover"),
  rivalJob: (id: string) => call<SignalJob>("GET", `/rival-jobs/${id}`),
  refreshSignals: () => call<SignalJob>("POST", "/signals/refresh"),
  signalJob: (id: string) => call<SignalJob>("GET", `/signal-jobs/${id}`),
  swotSettings: () => call<SwotParamsAll>("GET", "/swot-settings"),
  saveSwotSettings: (company: string, p: Omit<SwotParams, "company">) => call<SwotParams>("PUT", `/swot-settings/${encodeURIComponent(company)}`, p),
  opportunities: (company: string) => call<Findings>("GET", "/opportunities" + q({ company })),
  opportunityCounts: () => call<{ counts: Record<string, number> }>("GET", "/opportunities" + q({ company: "All" })),
  decideFinding: (id: number, status: Finding["status"]) => call<Finding>("PATCH", `/opportunities/${id}`, { status }),
  runOpportunities: (company: string) => call<SignalJob>("POST", `/opportunities/${encodeURIComponent(company)}/run`),
  opportunityJob: (id: string) => call<SignalJob & { result: { findings: number; news: number; errors: string[] } | null }>("GET", `/opportunity-jobs/${id}`),
  caseDetail: (id: string) => call<CaseDetail>("GET", `/cases/${encodeURIComponent(id)}`),
  signals: (company: string, status: SignalStatus) => call<SignalList>("GET", "/signals" + q({ company, status })),
  setStatus: (id: string, status: SignalStatus) => call<CaseSummary>("POST", `/cases/${encodeURIComponent(id)}/status`, { status }),
  thesis: (id: string, company?: string) => call<{ company: string; signal: CaseDetail; thesis: ThesisDoc | null; failed: { error: string; at: string } | null }>("GET", `/cases/${encodeURIComponent(id)}/thesis` + q({ company })),
  writeThesis: (id: string, company?: string) => call<SignalJob>("POST", `/cases/${encodeURIComponent(id)}/thesis` + q({ company })),
  thesisJob: (id: string) => call<SignalJob>("GET", `/thesis-jobs/${id}`),
  competitors: (company: string) => call<{ company: string; rivals: Rival[] }>("GET", "/competitors" + q({ company })),
  overview: (id: number, company: string) => call<Overview>("GET", `/competitors/${id}/overview` + q({ company })),
  writeOverview: (id: number, company: string) => call<SignalJob>("POST", `/competitors/${id}/overview` + q({ company })),
  overviewJob: (id: string) => call<SignalJob>("GET", `/profile-jobs/${id}`),
  market: (company: string) => call<Market>("GET", "/market" + q({ company })),
  marketRefresh: (company: string) => call<SignalJob>("POST", "/market/refresh" + q({ company })),
  marketJob: (id: string) => call<SignalJob>("GET", `/market-jobs/${id}`),
  deals: (company: string) => call<{ deals: Deal[] }>("GET", "/deals" + q({ company })),
  askStart: (company: string) => call<{ suggestions: string[] }>("GET", "/ask" + q({ company })),
  ask: (company: string, question: string) => call<any>("POST", "/ask", { company, question }),
  theses: () => call<any[]>("GET", "/theses"),
  parseThesis: (text: string) => call<any>("POST", "/theses/parse", { text }),
  saveThesis: (desk: string, text: string, c: unknown) => call<any>("POST", "/theses", { desk, text, c }),
  triggers: () => call<any[]>("GET", "/triggers"),
  addTrigger: (t: { desk: string; op: string; val: number; company: string }) => call<any>("POST", "/triggers", { ...t, metric: "score" }),
  toggleTrigger: (id: string, on: boolean) => call<any>("PATCH", `/triggers/${id}`, { on }),
  deleteTrigger: (id: string) => call<void>("DELETE", `/triggers/${id}`),
  universe: () => call<any[]>("GET", "/universe"),
  addUniverse: (company: string, desk: string) => call<any>("POST", "/universe", { company, desk }),
  activity: () => call<any[]>("GET", "/activity"),
};

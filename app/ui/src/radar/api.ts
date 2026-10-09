// Thin client for the radar screens' API (/api/v1/radar, backend app/radar/api.py).
/* eslint-disable @typescript-eslint/no-explicit-any */

import { TOKEN_KEY } from "../services/api";

export interface Me { name: string; role: string; companies: string[]; group_view: boolean }

export type Stage = "digest" | "deep" | "decide" | "act" | "closed";

export interface CaseSummary {
  id: string;
  kind: "deal" | "threat";
  who: string;
  title: string;
  company: string;
  companies: string[];
  stage: Stage;
  in_book: boolean;
  owner: string | null;
  outcome: string | null;
  date: string;
  status_label: string;
  score?: number;
  threat?: string;
  threat_class?: string;
  chips: string[];
}

export interface Signal { date: string; label: string; text: string; source: string }

export interface QuickLook {
  story?: string;
  signals?: Signal[];
  score?: { parts: [string, number][]; base: number; m: number; capped: boolean; score: number; n_types: number };
  thesis?: { company: string; checks: [string, boolean][]; ok: number; total: number } | null;
  owners?: [string, number, string][];
  bidders?: string[];
  analyst?: string;
  timeline?: Signal[];
  spark?: Spark;
  voc_top?: { sentiment: string; topic: string; text: string };
}

export interface CaseDetail extends CaseSummary { quick: QuickLook }

export interface Spark { t: string; v: number[]; a: string; b: string }
export interface Tone { t: string; v: number[] }

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

export interface SwotSource { id: string; text: string; source: string; date: string | null; url: string | null; origin: "live" | "demo" | "team"; origin_label: string }
export interface SwotItem { id: string; text: string; case_id?: string | null; reasoning: string | null; sources: SwotSource[] }
export interface SwotMethod { built_by: "demo" | "agent"; summary: string; steps: string[]; model?: string; at?: string; rounds?: number; live_signals_available: number }
export interface SwotView { company: string; S: SwotItem[]; W: SwotItem[]; O: SwotItem[]; T: SwotItem[]; moves: number; set_aside: number; source: { by: "mock" | "agent"; model?: string; at?: string }; method: SwotMethod }

// The Executive Dashboard's data source — SWOT scoped to only the subsidiaries with a real
// signal in one weekly digest (see app/radar/bridge.py:digest_swot_summary).
export interface DigestSwotSubsidiary { co: string; code: string; signal_count: number; swot: SwotView }
export interface DigestSwot { digest: { id: number; period_start: string; period_end: string } | null; subsidiaries: DigestSwotSubsidiary[] }
export interface Position { id: string; q: "O" | "T"; text: string; case_id: string | null; impact: number; urgency: number; used: boolean; move: string | null }

export interface Home {
  scope: string;
  week: string;
  analyst: string;
  recommended: RecCard[];
  set_aside: { co: string; case_id: string; why: string; who: string }[];
  swot: SwotView | null;
  positions: Position[] | null;
  tiles: SwotView[] | null;
  signals: { date: string; who: string; label: string; text: string; case_id: string }[];
  signal_count: number;
}

export interface Job {
  id: string;
  status: "running" | "completed";
  items: { case_id: string; who: string; title: string; done_steps: number; total_steps: number; current: { task: string; agent: string } | null }[];
}

export interface SwotJob { id: string; company: string; status: "running" | "completed" | "failed"; round: number; max_rounds: number; error: string | null }

export interface SignalsStatus {
  sources: { name: string; configured: boolean; note?: string }[];
  companies: { company: string; rival_placeholder: string; real_name: string | null; rival_source: "auto" | "manual" | null; stock_symbol: string | null;
    rivals_found: { name: string; why: string; status?: "proposed" | "watching"; sources: { title: string; url: string }[] }[]; rivals_found_at: string | null; live_signals: number; gate_open?: boolean }[];
  last_refresh: string | null;
  errors: string[];
}

export interface SchedulerStatus {
  enabled: boolean; signals_at: string; rivals_every_days: number; auto_rebuild: boolean; running: string | null; last_error: string | null;
  last: { rivals: string | null; signals: string | null }; next: { rivals: string; signals: string } | null;
}

export interface SignalJob { id: string; status: "running" | "completed" | "failed"; result: { companies: string[]; signals: number; errors: string[] } | null; error: string | null }

export interface PlanStep { when: string; what: string; how: string; done?: boolean }

export interface Overview {
  id: string;
  kind: "deal" | "threat";
  title: string;
  who: string;
  company: string;
  written: string;
  stage: Stage;
  owner: string | null;
  approved: string | null;
  outcome: string | null;
  owners: string[];
  plan: PlanStep[];
  why?: { company: string; title: string; uses: { id: string; text: string }[] };
  recommendation: { title: string; text: string; decision: string; confidence: number };
  glance: [string, string][];
  sources: string[];
  // deal
  story?: string;
  signals?: Signal[];
  impact?: [string, string];
  pros?: string[];
  thesis?: [string, boolean][];
  health?: { verdict: [string, string]; revenue: number[]; margin: number[]; years: string[]; kv: [string, string][]; checks: { bad: boolean; text: string }[] };
  scenario?: any;
  graph?: { name: string; score: number; owners: [string, number, string][]; directors: [string, string, string[]][]; subs: string[] };
  risks?: string[];
  flags?: string[];
  questions?: string[];
  // threat
  timeline?: Signal[];
  analyst?: string;
  suggest?: string;
  market?: { rival_return: number; base_return: number; base_name: string; why: string; act: string } | null;
  voc?: { sentiment: string; topic: string; text: string; mentions: number }[];
  opening?: string;
  options?: { recommended: boolean; title: string; text: string; impact: string; cost: string; risk: string }[];
}

export interface FollowUp extends CaseSummary {
  approved: string;
  plan: PlanStep[];
  updates: { date: string; text: string; fresh: boolean }[];
  watching: string[];
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

// The radar API sits behind the named-reviewer login: send the same token the rest of the app
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
  companies: () => call<{ name: string; rival: string; segment: string }[]>("GET", "/companies"),
  home: (company: string) => call<Home>("GET", "/home" + q({ company })),
  digestSwot: (digestId?: number) =>
    call<DigestSwot>("GET", "/digest-swot" + (digestId !== undefined ? q({ digest_id: String(digestId) }) : "")),
  rebuildSwot: (company: string) => call<SwotJob>("POST", `/swot/${encodeURIComponent(company)}/rebuild`),
  swotJob: (id: string) => call<SwotJob>("GET", `/swot-jobs/${id}`),
  signalsStatus: () => call<SignalsStatus>("GET", "/signals/status"),
  scheduler: () => call<SchedulerStatus>("GET", "/scheduler"),
  findRivals: () => call<SignalJob>("POST", "/rivals/discover"),
  rivalJob: (id: string) => call<SignalJob>("GET", `/rival-jobs/${id}`),
  refreshSignals: () => call<SignalJob>("POST", "/signals/refresh"),
  signalJob: (id: string) => call<SignalJob>("GET", `/signal-jobs/${id}`),
  caseDetail: (id: string) => call<CaseDetail>("GET", `/cases/${encodeURIComponent(id)}`),
  startDeepDive: (case_ids: string[], company: string) => call<Job>("POST", "/deep-dives", { case_ids, company }),
  job: (id: string) => call<Job>("GET", `/deep-dives/${id}`),
  book: () => call<{ week: string; written: string; pages: (CaseSummary & { recommendation: string })[] }>("GET", "/book"),
  overview: (id: string) => call<Overview>("GET", `/cases/${encodeURIComponent(id)}/overview`),
  decide: (id: string, action: "approve" | "park" | "reject", owner: string | undefined, company: string) =>
    call<CaseSummary>("POST", `/cases/${encodeURIComponent(id)}/decision`, { action, owner, company }),
  followUps: (company: string) => call<FollowUp[]>("GET", "/follow-ups" + q({ company })),
  planStep: (id: string, i: number, done: boolean, company: string) => call<FollowUp>("PATCH", `/cases/${encodeURIComponent(id)}/plan/${i}`, { done, company }),
  simulateWeek: (id: string, company: string) => call<FollowUp>("POST", `/cases/${encodeURIComponent(id)}/simulate-week`, { company }),
  outcome: (id: string, outcome: "acted" | "dropped", company: string) => call<FollowUp>("POST", `/cases/${encodeURIComponent(id)}/outcome`, { outcome, company }),
  competitors: (company: string) => call<{ company: string; rivals: any[] }>("GET", "/competitors" + q({ company })),
  follow: (company: string, rival: string, follow: boolean) => call<{ company: string; rivals: any[] }>("POST", "/competitors/follow", { company, rival, follow }),
  market: (company: string, rival: string | undefined, period: string) => call<any>("GET", "/market" + q({ company, rival, period })),
  deals: (company: string) => call<any>("GET", "/deals" + q({ company })),
  askStart: (company: string) => call<any>("GET", "/ask" + q({ company })),
  ask: (company: string, question: string) => call<any>("POST", "/ask", { company, question }),
  theses: () => call<any[]>("GET", "/theses"),
  parseThesis: (text: string) => call<any>("POST", "/theses/parse", { text }),
  saveThesis: (desk: string, text: string, c: unknown) => call<any>("POST", "/theses", { desk, text, c }),
  triggers: () => call<any[]>("GET", "/triggers"),
  addTrigger: (t: Record<string, string>) => call<any>("POST", "/triggers", t),
  toggleTrigger: (id: string, on: boolean) => call<any>("PATCH", `/triggers/${id}`, { on }),
  deleteTrigger: (id: string) => call<void>("DELETE", `/triggers/${id}`),
  universe: () => call<any[]>("GET", "/universe"),
  addUniverse: (company: string, desk: string) => call<any>("POST", "/universe", { company, desk }),
  activity: () => call<any[]>("GET", "/activity"),
  reset: () => call<{ ok: boolean }>("POST", "/demo/reset"),
};

import axios from "axios";
import toast from "react-hot-toast";

import type {
  AuditLogEntry,
  DigestDetail,
  DigestSummary,
  EntityOut,
  EscalationBrief,
  IngestRunResult,
  Job,
  Reviewer,
  ReviewerCreate,
  SignalClusterDetail,
  SignalClusterSummary,
  SourcesStatus,
  Subsidiary,
  SwotBrief,
  TeamNotes,
  TokenResponse,
  User,
  WatchlistEntity,
} from "../types";

export const TOKEN_KEY = "hr_token";

// In dev, Vite proxies /api -> VITE_API_URL. In production, the nginx
// container proxies /api -> BACKEND_URL. The app always calls the relative
// /api/v1 base — the backend's routers are registered under /api/v1/*.
const api = axios.create({
  baseURL: "/api/v1",
});

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
}

// Rehydrate the axios header immediately on module load if a token is already
// sitting in localStorage (e.g. on a hard page refresh).
const existingToken = localStorage.getItem(TOKEN_KEY);
if (existingToken) {
  setAuthToken(existingToken);
}

// A callback the AuthContext registers so the interceptor can force a logout
// / redirect without this module needing to know about React Router.
let onUnauthorized: () => void = () => {};
export function registerUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      setAuthToken(null);
      onUnauthorized();
    } else if (status === 403) {
      toast.error("You don't have access to this action");
    }
    return Promise.reject(error);
  }
);

export default api;

// ---- Auth ----
export const login = (email: string, password: string) =>
  api.post<TokenResponse>("/auth/login", { email, password }).then((r) => r.data);
export const getMe = () => api.get<User>("/auth/me").then((r) => r.data);

// ---- Subsidiaries ----
export const getSubsidiaries = () => api.get<Subsidiary[]>("/subsidiaries").then((r) => r.data);
export const patchSubsidiaryGate = (code: string, compliance_gate: boolean) =>
  api.patch<Subsidiary>(`/subsidiaries/${code}/gate`, { compliance_gate }).then((r) => r.data);

// ---- Entities ----
export const getEntities = (subsidiary?: string) =>
  api.get<EntityOut[]>("/entities", { params: subsidiary ? { subsidiary } : {} }).then((r) => r.data);

// ---- Signals ----
export interface GetSignalsParams {
  subsidiary?: string;
  status?: string;
}

export const getSignals = (params?: GetSignalsParams) =>
  api.get<SignalClusterSummary[]>("/signals", { params }).then((r) => r.data);
export const getSignal = (id: number | string) =>
  api.get<SignalClusterDetail>(`/signals/${id}`).then((r) => r.data);
export const markUnderEvaluation = (id: number | string) =>
  api.post<SignalClusterDetail>(`/signals/${id}/mark-under-evaluation`).then((r) => r.data);
export const getEscalationBrief = (id: number | string) =>
  api.get<EscalationBrief>(`/signals/${id}/escalation-brief`).then((r) => r.data);

// ---- Digests ----
export const getDigests = () => api.get<DigestSummary[]>("/digests").then((r) => r.data);
export const getDigest = (id: number | string) =>
  api.get<DigestDetail>(`/digests/${id}`).then((r) => r.data);
export const generateDigest = () => api.post<DigestDetail>("/digests/generate").then((r) => r.data);

// ---- Background jobs ----
export const getJob = <R,>(id: string) => api.get<Job<R>>(`/jobs/${id}`).then((r) => r.data);

// Poll a job every `everyMs` until it finishes. Resolves with the finished job
// (completed or failed); rejects only if polling itself fails.
export async function waitForJob<R>(job: Job<R>, everyMs = 2000): Promise<Job<R>> {
  let current = job;
  while (current.status === "running") {
    await new Promise((resolve) => setTimeout(resolve, everyMs));
    current = await getJob<R>(current.id);
  }
  return current;
}

// ---- Ingest ----
// Starts a run in the background (202); poll it with waitForJob.
export const runIngest = () => api.post<Job<IngestRunResult>>("/ingest/run").then((r) => r.data);

// ---- Watchlist (compliance_admin) ----
export const getWatchlist = () => api.get<WatchlistEntity[]>("/watchlist").then((r) => r.data);
export const updateWatchlistEntity = (
  id: number,
  payload: { status?: "watching" | "dismissed"; nse_symbol?: string; query_name?: string }
) => api.patch<WatchlistEntity>(`/watchlist/${id}`, payload).then((r) => r.data);
export const addWatchlistEntity = (payload: {
  name: string;
  sectors: string[];
  category?: string;
  nse_symbol?: string;
  query_name?: string;
}) => api.post<WatchlistEntity>("/watchlist", payload).then((r) => r.data);
export interface DiscoveryResult {
  subsidiaries: string[];
  proposed: string[];
  refreshed: string[];
  errors: string[];
}
export const runDiscovery = () => api.post<Job<DiscoveryResult>>("/watchlist/discover").then((r) => r.data);
export const getSourcesStatus = () => api.get<SourcesStatus>("/watchlist/sources").then((r) => r.data);

// ---- SWOT briefs ----
export const getSwot = (code: string) => api.get<SwotBrief>(`/swot/${code}`).then((r) => r.data);
export const rebuildSwot = (code: string) => api.post<Job>(`/swot/${code}/rebuild`).then((r) => r.data);
export const getTeamNotes = (code: string) => api.get<TeamNotes>(`/swot/${code}/team-notes`).then((r) => r.data);
export const putTeamNotes = (code: string, notes: TeamNotes) =>
  api.put<TeamNotes>(`/swot/${code}/team-notes`, notes).then((r) => r.data);

// ---- Reviewers ----
export const getReviewers = () => api.get<Reviewer[]>("/reviewers").then((r) => r.data);
export const createReviewer = (payload: ReviewerCreate) =>
  api.post<Reviewer>("/reviewers", payload).then((r) => r.data);
export const deleteReviewer = (id: number) =>
  api.delete<Reviewer>(`/reviewers/${id}`).then((r) => r.data);

// ---- Audit log ----
export const getAuditLog = (limit = 100) =>
  api.get<AuditLogEntry[]>("/audit-log", { params: { limit } }).then((r) => r.data);

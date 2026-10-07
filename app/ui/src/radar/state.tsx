import { createContext, useContext } from "react";

export type View = "signals" | "competitors" | "ask" | "shortlist" | "settings" | "self" | "digest" | "finance";

export interface AppState {
  view: View;
  go: (v: View) => void;
  /** The RPG companies (every user sees all of them). */
  companies: string[];
  /** "All" or one RPG company. */
  scope: string;
  setScope: (s: string) => void;
  /** Company used by per-company screens when scope is "All" (the last one picked). */
  cur: string;
  /** Open M&A Signals at one signal's acquisition thesis. */
  openSignal: (caseId: string) => void;
  signalSel: string | null;
  clearSignalSel: () => void;
  /** Open Competitor Analysis at one watched company's case, with its detailed news. */
  openRow: (caseId: string, home?: string) => void;
  focus: string | null;
  clearFocus: () => void;
  toast: (msg: string) => void;
  /** Bumped after every change so screens refetch. */
  version: number;
  bump: () => void;
  user: string;
}

export const Ctx = createContext<AppState>(null as unknown as AppState);
export const useApp = () => useContext(Ctx);

export const slug = (id: string) => id.replace(/\W/g, "_");

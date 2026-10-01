import { createContext, useContext } from "react";

export type View = "home" | "deep" | "book" | "follow" | "comp" | "fin" | "deals" | "ask" | "thesis" | "trig" | "admin";

export const COMPANIES = ["CEAT", "KEC", "Zensar", "RPG Life Sciences", "Raychem RPG", "Harrisons"];

export interface AppState {
  view: View;
  go: (v: View) => void;
  /** The RPG companies this reviewer may open: in their scope with an open compliance gate. */
  companies: string[];
  /** Only a compliance_admin gets the group-wide "All" view. */
  groupView: boolean;
  /** "All" or one RPG company. */
  scope: string;
  setScope: (s: string) => void;
  /** Company used by per-company screens when scope is "All" (the last one picked). */
  cur: string;
  shortlist: string[];
  toggleShortlist: (id: string, on: boolean) => boolean;
  clearShortlist: () => void;
  escalate: () => Promise<void>;
  jobId: string | null;
  bookPage: number;
  setBookPage: (p: number) => void;
  openBookAt: (caseId: string) => void;
  followSel: string | null;
  openFollowUp: (caseId: string) => void;
  /** Go to This week, expand a case and scroll to it. */
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

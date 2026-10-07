import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { PageMetaProvider, usePageMetaContext } from "../context/PageMetaContext";
import { api, type Me } from "./api";
import { AskRadar } from "./pages/Ask";
import Competitors from "./pages/Competitors";
import Digest from "./pages/Digest";
import Finance from "./pages/Finance";
import SelfAnalysis from "./pages/Self";
import { RadarSettings } from "./pages/Settings";
import Shortlist from "./pages/Shortlist";
import Signals from "./pages/Signals";
import { Ctx, type AppState, type View } from "./state";
import "./styles.css";

const NAV: [string, [View, string][]][] = [
  ["Radar", [["signals", "M&A Signals"], ["competitors", "Competitor Analysis"], ["ask", "Ask Radar"], ["shortlist", "Shortlisted signals"], ["settings", "Radar settings"]]],
  ["Self reflection", [["self", "Self analysis"], ["digest", "Weekly digest"], ["finance", "The financial market"]]],
];

// Workspace: the repo's desk screens (ZenLabs design, rendered inside a .tw wrapper).
const DESK: [string, string][] = [
  ["/digests", "Digest archive"],
  ["/admin", "Users and watchlist"],
];

function initialTheme(): "light" | "dark" {
  try { const t = localStorage.getItem("hr-theme"); if (t === "light" || t === "dark") return t; } catch { /* storage blocked */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** The page title the ZenLabs screens set with usePageMeta, shown above them. */
function DeskTitle() {
  const { meta } = usePageMetaContext();
  return (
    <div className="desk-head">
      <h1>{meta.title}</h1>
      {meta.subtitle && <p className="sub">{meta.subtitle}</p>}
    </div>
  );
}

export default function RadarApp() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const onDesk = location.pathname !== "/";

  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [view, setView] = useState<View>("signals");
  const [scope, setScopeRaw] = useState("CEAT");
  const [cur, setCur] = useState("CEAT");
  const [signalSel, setSignalSel] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [theme, setTheme] = useState(initialTheme);
  const [counts, setCounts] = useState({ signals: 0, shortlist: 0, digest: 0 });
  const toastTimer = useRef<number>();

  // Who is signed in, and the RPG companies (every user sees all of them).
  useEffect(() => {
    api.me().then((m) => {
      setMe(m);
      const first = m.companies.includes("CEAT") ? "CEAT" : m.companies[0];
      if (first) { setScopeRaw(first); setCur(first); }
    }).catch((e) => setMeError((e as Error).message));
  }, []);
  const companies = me?.companies ?? [];

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("hr-theme", theme); } catch { /* storage blocked */ }
  }, [theme]);

  const toast = useCallback((m: string) => {
    setToastMsg(m); window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastMsg(null), 2600);
  }, []);
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const go = useCallback((v: View) => {
    setView(v);
    if (window.location.pathname !== "/") navigate("/");
    window.scrollTo(0, 0);
  }, [navigate]);
  const setScope = useCallback((s: string) => { setScopeRaw(s); if (s !== "All") setCur(s); }, []);
  const who = user?.name || "Reviewer";

  // Counts for the side menu.
  useEffect(() => {
    if (!me || !companies.length) return;
    Promise.all([api.signals(scope, "open"), api.opportunityCounts()]).then(([sg, o]) => {
      setCounts({ signals: sg.counts.open, shortlist: sg.counts.shortlisted,
                  digest: scope === "All" ? Object.values(o.counts).reduce((a, n) => a + n, 0) : o.counts[scope] || 0 });
    }).catch(() => undefined);
  }, [scope, version, me]);

  const state: AppState = useMemo(() => ({
    view, go, companies, scope, setScope, cur, user: who, version, bump, toast, focus, signalSel,
    openSignal: (id) => { setSignalSel(id); go("signals"); },
    clearSignalSel: () => setSignalSel(null),
    openRow: (id, home) => {
      // Stay on the current company if it watches this one; otherwise switch to a company that does.
      api.caseDetail(id).then((c) => {
        const target = home && c.companies.includes(home) ? home : c.companies.find((x) => companies.includes(x));
        if (!c.companies.includes(cur) && target) setScope(target);
        setFocus(id); go("competitors");
      }).catch((e) => toast((e as Error).message));
    },
    clearFocus: () => setFocus(null),
  }), [view, scope, cur, version, focus, signalSel, who, companies]);

  const navCount: Partial<Record<View, number>> = { signals: counts.signals, shortlist: counts.shortlist, digest: counts.digest };
  const active = onDesk ? null : view;

  return (
    <Ctx.Provider value={state}>
      <PageMetaProvider>
        <div className="radar-root">
          <div className="shell-top">
            <div className="brand">
              <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.4" /><circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M8 8 L13 3" stroke="currentColor" strokeWidth="1.6" /></svg>
              Horizon Radar
            </div>
            {!onDesk && companies.length > 0 && (
              <div className="topctl">
                <label htmlFor="coSel">Company</label>
                <select id="coSel" value={scope} onChange={(e) => setScope(e.target.value)}>
                  <option value="All">All companies</option>
                  {companies.map((c) => <option key={c}>{c}</option>)}
                </select>
              </div>
            )}
            <span className="spacer" />
            <button type="button" className="btnx" id="themeBtn" aria-pressed={theme === "dark"} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "☀︎" : "☾"}</button>
            <button type="button" className="btnx" onClick={logout}>Sign out</button>
          </div>
          <div className="restricted-bar" role="note">
            <b>Restricted — UPSI-adjacent — do not forward.</b> A signal-flagging tool, not a valuation or due-diligence tool. Every view is logged.
          </div>
          <div className="shell">
            <nav className="side" aria-label="Screens">
              {NAV.map(([grp, items]) => (
                <div key={grp} style={{ display: "contents" }}>
                  <div className="navgrp">{grp}</div>
                  {items.map(([k, l]) => (
                    <button key={k} className="navbtn" aria-current={k === active ? "page" : undefined} onClick={() => go(k)}>
                      <span>{l}</span>{navCount[k] !== undefined && <em>{navCount[k]}</em>}
                    </button>
                  ))}
                </div>
              ))}
              <div className="navgrp">Workspace</div>
              {DESK.map(([path, label]) => (
                <button key={path} className="navbtn" aria-current={location.pathname.startsWith(path) || (path === "/digests" && location.pathname.startsWith("/signals")) ? "page" : undefined}
                  onClick={() => navigate(path)}>
                  <span>{label}</span>
                </button>
              ))}
              <div className="sep">Signed in: {who}</div>
            </nav>
            <main className="am" id="main">
              {onDesk ? (
                <section className="view desk tw">
                  <DeskTitle />
                  <Outlet />
                </section>
              ) : meError ? (
                <section className="view"><p className="sub">{meError}</p></section>
              ) : !me ? (
                <section className="view"><p className="sub">Loading…</p></section>
              ) : (
                <section className="view">
                  {view === "signals" && <Signals />}
                  {view === "competitors" && <Competitors />}
                  {view === "ask" && <AskRadar />}
                  {view === "shortlist" && <Shortlist />}
                  {view === "settings" && <RadarSettings />}
                  {view === "self" && <SelfAnalysis />}
                  {view === "digest" && <Digest />}
                  {view === "finance" && <Finance />}
                </section>
              )}
            </main>
          </div>
          {toastMsg && <div className="toast" role="status" aria-live="polite">{toastMsg}</div>}
        </div>
      </PageMetaProvider>
    </Ctx.Provider>
  );
}

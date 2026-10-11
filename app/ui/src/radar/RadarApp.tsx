import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { LayoutGrid, LogOut, Radar, ShieldCheck, type LucideIcon } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { PageMetaProvider, usePageMetaContext } from "../context/PageMetaContext";
import { api, type CaseSummary, type Me } from "./api";
import Book from "./pages/Book";
import DeepDive from "./pages/DeepDive";
import { AskRadar, Competitors, Market, RivalDeals } from "./pages/Explore";
import FollowUp from "./pages/FollowUp";
import Home from "./pages/Home";
import { Theses, Watched, WatchRules } from "./pages/Settings";
import { COMPANIES, Ctx, type AppState, type View } from "./state";
import "./styles.css";

// Nav deliberately collapsed to two destinations: the Executive Dashboard
// (the digest/SWOT/ripple story) and Admin (org-wide compliance config, not
// subsidiary analysis). Every other screen — This week, Deep-dive book,
// Follow-up, Competitors, Market, Rival deals, Ask Radar, Signal board,
// Acquisition theses, Watch rules, Watched companies, Digest archive — is
// still fully functional, just no longer a standing nav item: they're
// reachable only via a subsidiary's "Deep dive to analyze" button on the
// dashboard, which lands on /analyze/:company (AnalysisWorkspace.tsx).
const TOP_LEVEL: [string, string, LucideIcon][] = [
  ["/dashboard", "Executive Dashboard", LayoutGrid],
];

const DESK: [string, string, boolean, LucideIcon][] = [
  ["/admin", "Admin", true, ShieldCheck],
];

/** The page title the desk screens set with usePageMeta, shown above them. */
function DeskTitle() {
  const { meta } = usePageMetaContext();
  return (
    <div className="desk-head">
      <h1>{meta.title}</h1>
      {meta.subtitle && <p className="sub">{meta.subtitle}</p>}
      <p className="desk-byline">Powered by ZenLabs Agent Foundry</p>
    </div>
  );
}

export default function RadarApp() {
  const { user, isAdmin, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const onDesk = location.pathname !== "/";

  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [view, setView] = useState<View>("home");
  const [scope, setScopeRaw] = useState("CEAT");
  const [cur, setCur] = useState("CEAT");
  const [shortlist, setShortlist] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [bookPage, setBookPage] = useState(0);
  const [followSel, setFollowSel] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [guideOn, setGuideOn] = useState(true);
  const [counts, setCounts] = useState({ home: 0, book: 0, follow: 0, pending: 0, openFollow: 0, jobRunning: false });
  const toastTimer = useRef<number>();

  // Which RPG companies this reviewer may open (scope + open gate); "All" only for admins.
  useEffect(() => {
    api.me().then((m) => {
      setMe(m);
      const first = m.companies.includes("CEAT") ? "CEAT" : m.companies[0];
      if (first) { setScopeRaw(first); setCur(first); }
    }).catch((e) => setMeError((e as Error).message));
  }, []);
  const companies = me?.companies ?? [];
  const groupView = !!me?.group_view;

  useEffect(() => { document.body.classList.toggle("guide-on", guideOn); }, [guideOn, onDesk]);

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

  // Counts for the side menu and the guided demo.
  useEffect(() => {
    if (!me || !companies.length) return;
    Promise.all([api.home(scope), api.book(), api.followUps(groupView ? "All" : scope)]).then(([h, b, f]) => {
      const digest = h.recommended.filter((r) => r.case.stage === "digest").length;
      setCounts({ home: digest, book: b.pages.length, follow: f.filter((x) => x.stage === "act").length,
        pending: b.pages.filter((p: CaseSummary) => p.stage === "decide").length,
        openFollow: f.filter((x) => x.in_book && x.stage === "act").length, jobRunning: false });
    }).catch(() => undefined);
  }, [scope, version, me]);

  const state: AppState = useMemo(() => ({
    view, go, companies, groupView, scope, setScope, cur, user: who, version, bump, toast, jobId, bookPage, setBookPage, followSel, focus,
    shortlist,
    toggleShortlist: (id, on) => {
      if (on && shortlist.length >= 5) { toast("Shortlist up to 5 companies at a time."); return false; }
      setShortlist((s) => (on ? [...s.filter((x) => x !== id), id] : s.filter((x) => x !== id)));
      return true;
    },
    clearShortlist: () => setShortlist([]),
    escalate: async () => {
      try {
        const j = await api.startDeepDive(shortlist, scope);
        setShortlist([]); setJobId(j.id); bump(); go("deep");
      } catch (e) { toast((e as Error).message); }
    },
    openBookAt: (id) => { api.book().then((b) => { const i = b.pages.findIndex((p) => p.id === id); setBookPage(i < 0 ? 0 : i + 1); go("book"); }); },
    openFollowUp: (id) => { setFollowSel(id); go("follow"); },
    openRow: (id, home) => {
      // Stay on the current company if it lists the case; otherwise switch to the company that recommends it.
      api.home(scope).then((h) => {
        const here = h.recommended.some((r) => r.case_id === id) || h.set_aside.some((s) => s.case_id === id);
        if (!here) {
          const target = home || (id.startsWith("t_") ? id.slice(2) : undefined);
          if (target && COMPANIES.includes(target) && companies.includes(target)) setScope(target);
          else api.caseDetail(id).then((c) => { if (companies.includes(c.company)) setScope(c.company); });
        }
        setFocus(id); go("home");
      });
    },
    clearFocus: () => setFocus(null),
  }), [view, scope, cur, version, jobId, bookPage, followSel, focus, shortlist, who, companies, groupView]);

  // ---------- guided demo ----------
  let g: { n: number; title: string; text: string; go?: [string, () => void] };
  if (view === "deep" && jobId) g = { n: 3, title: "Deep dive", text: "Agents are writing one page per shortlisted company. Only these companies get the paid data and deeper research." };
  else if (shortlist.length) g = { n: 2, title: "Escalate", text: `${shortlist.length} shortlisted. Add up to 5, then press Escalate in the bar at the bottom.`, go: view !== "home" ? ["Back to This week", () => go("home")] : undefined };
  else if (counts.pending) g = { n: 4, title: "Read the book", text: "One page per company, like a book. Turn pages with Next or the arrow keys. Each page ends with a decision: approve with an owner, park or reject.", go: view !== "book" ? ["Open the book", () => go("book")] : undefined };
  else if (counts.openFollow) g = { n: 5, title: "Follow up", text: "Approved companies get a tracked plan and watch rules. Tick a step, press 'Simulate next week's run', then record the outcome.", go: view !== "follow" ? ["Open follow-up", () => go("follow")] : undefined };
  else if (counts.book) g = { n: 5, title: "That's the full story", text: "From each company's SWOT to a shortlist, a book of decisions and follow-up. Restart to try it with other companies." };
  else g = { n: 1, title: "Start with the SWOT", text: "Each RPG company's SWOT is rebuilt from the signals. Only moves that link a strength or weakness to an opportunity or threat are recommended. Hover a move to see its SWOT items, then tick Shortlist on 2 or 3.", go: view !== "home" ? ["Go to This week", () => go("home")] : undefined };

  const deskTip: { title: string; text: string } | null = location.pathname.startsWith("/dashboard")
    ? { title: "This week, by subsidiary", text: "Pick a week above. Each card is a subsidiary that actually had an M&A-potential signal that week — not every subsidiary, every week. Click \"Deep dive to analyze\" to see everything on it." }
    : location.pathname.startsWith("/analyze/")
    ? { title: "Everything on this subsidiary", text: "Switch tabs above — SWOT, the deep-dive dossier, follow-up, research tools, Signal board and Ripple effect — all scoped to this one subsidiary." }
    : null;

  const restart = async () => {
    try { await api.reset(); } catch (e) { toast((e as Error).message); return; }
    setShortlist([]); setJobId(null); setBookPage(0); setFollowSel(null); setScope(companies[0] || "CEAT"); go("home"); bump();
    toast("Demo reset to the start of the week.");
  };

  return (
    <Ctx.Provider value={state}>
      <PageMetaProvider>
        <div className="radar-root">
          <aside className="side">
            <div className="side-brand">
              <span className="logo"><Radar size={18} aria-hidden="true" /></span>
              Horizon Radar
            </div>
            <nav className="side-nav" aria-label="Screens">
              {TOP_LEVEL.map(([path, label, Icon]) => (
                <button key={path} className="navbtn" aria-current={location.pathname.startsWith(path) ? "page" : undefined}
                  onClick={() => navigate(path)}>
                  <Icon size={18} aria-hidden="true" />
                  <span>{label}</span>
                </button>
              ))}
              <div className="navgrp">Restricted desk</div>
              {DESK.filter(([, , adminOnly]) => isAdmin || !adminOnly).map(([path, label, , Icon]) => (
                <button key={path} className="navbtn" aria-current={location.pathname.startsWith(path) ? "page" : undefined}
                  onClick={() => navigate(path)}>
                  <Icon size={18} aria-hidden="true" />
                  <span>{label}</span>
                </button>
              ))}
            </nav>
            {guideOn && me && (onDesk ? (
              deskTip && (
                <div className="guide" role="region" aria-label="Guided demo">
                  <small>Guided demo</small>
                  <b>{deskTip.title}</b><p>{deskTip.text}</p>
                  <div className="gb">
                    <button onClick={() => setGuideOn(false)}>Hide guide</button>
                  </div>
                </div>
              )
            ) : (
              <div className="guide" role="region" aria-label="Guided demo">
                <small>Guided demo · step {g.n} of 5</small>
                <div className="gdots">{[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= g.n ? "on" : ""} />)}</div>
                <b>{g.title}</b><p>{g.text}</p>
                <div className="gb">
                  {g.go && <button className="pri" onClick={g.go[1]}>{g.go[0]}</button>}
                  {isAdmin && <button onClick={restart}>Restart</button>}
                  <button onClick={() => setGuideOn(false)}>Hide guide</button>
                </div>
              </div>
            ))}
            <div className="side-foot">Powered by ZenLabs Agent Foundry</div>
          </aside>
          <div className="main-col">
            <header className="shell-top">
              <div className="hd-title">
                <div className="eyebrow"><i aria-hidden="true" />RPG Corporate Strategy</div>
                <div className="hd-name gradient-text">Competitor and M&amp;A Signals</div>
              </div>
              <div className="hd-right">
                {!onDesk && companies.length > 0 && (
                  <div className="topctl">
                    <label htmlFor="coSel">Company</label>
                    <select id="coSel" value={scope} onChange={(e) => setScope(e.target.value)}>
                      {groupView && <option value="All">All companies</option>}
                      {companies.map((c) => <option key={c}>{c}</option>)}
                    </select>
                  </div>
                )}
                <span className="hd-pill" title="Signals of approved real companies are live. Rival placeholders, deal targets and decisions are demo data.">Live and demo data</span>
                <button type="button" className="btnx" aria-pressed={guideOn} onClick={() => setGuideOn(!guideOn)}>Guided demo</button>
                <div className="userchip">
                  <b>{who}</b>
                  <span>{isAdmin ? "Compliance admin" : "Strategy reviewer"}</span>
                </div>
                <button type="button" className="iconbtn" onClick={logout} title="Sign out" aria-label="Sign out"><LogOut size={17} /></button>
              </div>
            </header>
            <div className="restricted-bar" role="note">
              <b>Restricted — UPSI-adjacent — do not forward.</b> A signal-flagging tool for named reviewers, not a valuation or due-diligence tool. Every view is logged.
            </div>
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
                <section className="view" key={view}>
                  {view === "home" && <Home />}
                  {view === "deep" && <DeepDive />}
                  {view === "book" && <Book />}
                  {view === "follow" && <FollowUp />}
                  {view === "comp" && <Competitors />}
                  {view === "fin" && <Market />}
                  {view === "deals" && <RivalDeals />}
                  {view === "ask" && <AskRadar />}
                  {view === "thesis" && <Theses />}
                  {view === "trig" && <WatchRules />}
                  {view === "admin" && <Watched />}
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

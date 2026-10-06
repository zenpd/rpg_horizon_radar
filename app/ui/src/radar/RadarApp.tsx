import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

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

const NAV: [string, [View, string][]][] = [
  ["Radar", [["home", "This week"], ["book", "Deep-dive book"], ["follow", "Follow-up"]]],
  ["Explore", [["comp", "Competitors"], ["fin", "Market performance"], ["deals", "Rival deals"], ["ask", "Ask Radar"]]],
  ["Radar settings", [["thesis", "Acquisition theses"], ["trig", "Watch rules"], ["admin", "Watched companies"]]],
];

// The repo's restricted M&A screens (ZenLabs design, rendered inside a .tw wrapper).
const DESK: [string, string, boolean][] = [
  ["/board", "Signal board", false],
  ["/digests", "Digest archive", false],
  ["/admin", "Admin", true],
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
  const [theme, setTheme] = useState(initialTheme);
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
  // The spine: a weekly digest of scouted M&A-potential signals (Restricted desk) feeds each
  // company's SWOT below; approving a move projects what that SWOT becomes post-acquisition, and
  // escalating a signal on the desk surfaces its ripple effect on sibling RPG subsidiaries. Every
  // step's copy below exists to keep a first-time viewer oriented to that one story, not a list of
  // unrelated screens.
  let g: { n: number; title: string; text: string; go?: [string, () => void] };
  if (view === "deep" && jobId) g = { n: 3, title: "Deep dive", text: "Agents are writing one page per shortlisted company. Only these companies get the paid data and deeper research." };
  else if (shortlist.length) g = { n: 2, title: "Escalate", text: `${shortlist.length} shortlisted. Add up to 5, then press Escalate in the bar at the bottom.`, go: view !== "home" ? ["Back to This week", () => go("home")] : undefined };
  else if (counts.pending) g = { n: 4, title: "Read the book", text: "One page per company, like a book. Each page ends with a decision: approve with an owner, park or reject. Approve a deal and its page gains a new section — the SWOT projected for after the acquisition closes.", go: view !== "book" ? ["Open the book", () => go("book")] : undefined };
  else if (counts.openFollow) g = { n: 5, title: "Follow up", text: "Approved companies get a tracked plan and watch rules. Tick a step, press 'Simulate next week's run', then record the outcome.", go: view !== "follow" ? ["Open follow-up", () => go("follow")] : undefined };
  else if (counts.book) g = { n: 6, title: "The rest of the story", text: "One more thing this week's digest does: on the Restricted desk, escalating a flagged signal writes an Escalation Brief — including its ripple effect on sibling RPG subsidiaries that share raw materials, byproducts or support functions with the acquirer.", go: ["See the ripple effect", () => navigate("/board")] };
  else g = { n: 1, title: "It starts with the weekly digest", text: "Live connectors scout M&A-potential signals into a weekly digest on the Restricted desk; each RPG company's SWOT below is rebuilt from that same evidence. Only moves that link a strength or weakness to an opportunity or threat are recommended — hover one to see its SWOT items, then tick Shortlist on 2 or 3.", go: view !== "home" ? ["Go to This week", () => go("home")] : undefined };

  const deskTip: { title: string; text: string } | null = !onDesk ? null
    : location.pathname.startsWith("/digests")
    ? { title: "The weekly digest", text: "Every gate-open subsidiary's scored signals at or above threshold are snapshotted here automatically, once a week — the same evidence each company's SWOT is rebuilt from." }
    : location.pathname.startsWith("/admin")
    ? { title: "Compliance control", text: "Sector gates, reviewer scopes and the audit trail. Nothing here touches scoring or the SWOT — it only governs who sees what, and when a sector's signals start flowing at all." }
    : { title: "Where the digest lands", text: "Flagged signals, scored and routed by subsidiary. Mark one under evaluation to generate its Escalation Brief — pros, cons and a ripple-effect section on which sibling subsidiaries it would affect." };

  const restart = async () => {
    try { await api.reset(); } catch (e) { toast((e as Error).message); return; }
    setShortlist([]); setJobId(null); setBookPage(0); setFollowSel(null); setScope(companies[0] || "CEAT"); go("home"); bump();
    toast("Demo reset to the start of the week.");
  };

  const navCount: Partial<Record<View, number>> = { home: counts.home, book: counts.book, follow: counts.follow };
  const active = onDesk ? null : view === "deep" ? "book" : view;

  const renderNavGroup = ([grp, items]: (typeof NAV)[number]) => (
    <div key={grp} style={{ display: "contents" }}>
      <div className="navgrp">{grp}</div>
      {items.map(([k, l]) => (
        <button key={k} className="navbtn" aria-current={k === active ? "page" : undefined} onClick={() => go(k)}>
          <span>{l}</span>{navCount[k] !== undefined && <em>{navCount[k]}</em>}
        </button>
      ))}
    </div>
  );

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
                  {groupView && <option value="All">All companies</option>}
                  {companies.map((c) => <option key={c}>{c}</option>)}
                </select>
              </div>
            )}
            <span className="spacer" />
            <button type="button" className="btnx" aria-pressed={guideOn} onClick={() => setGuideOn(!guideOn)}>Guided demo</button>
            <button type="button" className="btnx" id="themeBtn" aria-pressed={theme === "dark"} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "☀︎" : "☾"}</button>
            <span className="mock" title="Approved real companies' signals are live; rival placeholders, deal targets and decisions are demo data">Live + demo data</span>
            <button type="button" className="btnx" onClick={logout}>Sign out</button>
          </div>
          <div className="restricted-bar" role="note">
            <b>Restricted — UPSI-adjacent — do not forward.</b> A signal-flagging tool for named reviewers, not a valuation or due-diligence tool. Every view is logged.
          </div>
          <div className="shell">
            <nav className="side" aria-label="Screens">
              {renderNavGroup(NAV[0])}
              {/* Where the weekly digest and the escalation/ripple-effect story live — right after
                  the per-company SWOT story, since both feed it, not after the secondary screens. */}
              <div className="navgrp">Restricted desk</div>
              {DESK.filter(([, , adminOnly]) => isAdmin || !adminOnly).map(([path, label]) => (
                <button key={path} className="navbtn" aria-current={location.pathname.startsWith(path) || (path === "/board" && location.pathname.startsWith("/signals")) ? "page" : undefined}
                  onClick={() => navigate(path)}>
                  <span>{label}</span>
                </button>
              ))}
              {NAV.slice(1).map(renderNavGroup)}
              <div className="sep">Signed in: {who}{isAdmin ? " · compliance admin" : ""}</div>
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
          {guideOn && me && (onDesk ? (
            <div className="guide" role="region" aria-label="Guided demo">
              <small>Guided demo · Restricted desk</small>
              <b>{deskTip!.title}</b><p>{deskTip!.text}</p>
              <div className="gb">
                <button className="pri" onClick={() => go("home")}>Back to This week</button>
                <button onClick={() => setGuideOn(false)}>Hide guide</button>
              </div>
            </div>
          ) : (
            <div className="guide" role="region" aria-label="Guided demo">
              <small>Guided demo · step {g.n} of 6</small>
              <div className="gdots">{[1, 2, 3, 4, 5, 6].map((i) => <i key={i} className={i <= g.n ? "on" : ""} />)}</div>
              <b>{g.title}</b><p>{g.text}</p>
              <div className="gb">
                {g.go && <button className="pri" onClick={g.go[1]}>{g.go[0]}</button>}
                {isAdmin && <button onClick={restart}>Restart</button>}
                <button onClick={() => setGuideOn(false)}>Hide guide</button>
              </div>
            </div>
          ))}
          {toastMsg && <div className="toast" role="status" aria-live="polite">{toastMsg}</div>}
        </div>
      </PageMetaProvider>
    </Ctx.Provider>
  );
}

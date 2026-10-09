import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Archive, BellRing, BookOpen, Briefcase, ClipboardCheck, Eye,
  LayoutGrid, LineChart, MessageCircleQuestion, Share2, Target, Users,
} from "lucide-react";

import { usePageMeta } from "../context/PageMetaContext";
import { useApp } from "../radar/state";
import Home from "../radar/pages/Home";
import Book from "../radar/pages/Book";
import FollowUp from "../radar/pages/FollowUp";
import { AskRadar, Competitors, Market, RivalDeals } from "../radar/pages/Explore";
import { Theses, Watched, WatchRules } from "../radar/pages/Settings";
import { getEscalationBrief, getSignals } from "../services/api";
import SignalCard from "../components/SignalCard";
import EscalationBriefView from "../components/EscalationBrief";
import type { EscalationBrief, SignalClusterSummary } from "../types";

// Radar company display name -> governed-backend subsidiary code (inverse of
// app/radar/bridge.py's CODE_TO_CO) — needed for the two tabs (Signal board,
// Ripple Effect) that read the governed-DB signal/escalation system rather
// than the radar in-memory STORE.
const CO_TO_CODE: Record<string, string> = {
  CEAT: "CEAT", KEC: "KEC", Zensar: "ZENSAR", "RPG Life Sciences": "RPGLS",
  "Raychem RPG": "RAYCHEM", Harrisons: "HARRISONS",
};

type TabKey = "swot" | "book" | "follow" | "board" | "ripple" | "comp" | "fin" | "deals" | "ask" | "thesis" | "trig" | "watched";

const TABS: { key: TabKey; label: string; icon: typeof LayoutGrid }[] = [
  { key: "swot", label: "SWOT", icon: LayoutGrid },
  { key: "book", label: "Deep-dive book", icon: BookOpen },
  { key: "follow", label: "Follow-up", icon: ClipboardCheck },
  { key: "board", label: "Signal board", icon: Archive },
  { key: "ripple", label: "Ripple effect", icon: Share2 },
  { key: "comp", label: "Competitors", icon: Users },
  { key: "fin", label: "Market performance", icon: LineChart },
  { key: "deals", label: "Rival deals", icon: Briefcase },
  { key: "ask", label: "Ask Radar", icon: MessageCircleQuestion },
  { key: "thesis", label: "Acquisition theses", icon: Target },
  { key: "trig", label: "Watch rules", icon: BellRing },
  { key: "watched", label: "Watched companies", icon: Eye },
];

function SignalBoardTab({ code }: { code: string }) {
  const [signals, setSignals] = useState<SignalClusterSummary[]>([]);
  const [status, setStatus] = useState<"live" | "under_evaluation">("live");

  useEffect(() => {
    getSignals({ subsidiary: code, status }).then(setSignals).catch(() => setSignals([]));
  }, [code, status]);

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {(["live", "under_evaluation"] as const).map((s) => (
          <button key={s} type="button" onClick={() => setStatus(s)}
            className={`btn btn-sm ${status === s ? "btn-restricted" : "btn-secondary"}`}>
            {s === "live" ? "Live" : "Under Evaluation"}
          </button>
        ))}
      </div>
      {signals.length === 0 ? (
        <div className="card p-8 text-center text-sm text-gray-500">No {status === "live" ? "live" : "under-evaluation"} signals for this subsidiary.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {signals.map((s) => <SignalCard key={s.id} signal={s} />)}
        </div>
      )}
    </div>
  );
}

function RippleEffectTab({ code }: { code: string }) {
  const [signals, setSignals] = useState<SignalClusterSummary[]>([]);
  const [briefs, setBriefs] = useState<Record<number, EscalationBrief>>({});

  useEffect(() => {
    getSignals({ subsidiary: code, status: "under_evaluation" }).then(async (list) => {
      setSignals(list);
      const entries = await Promise.all(list.map(async (s) => [s.id, await getEscalationBrief(s.id).catch(() => null)] as const));
      setBriefs(Object.fromEntries(entries.filter(([, b]) => b) as [number, EscalationBrief][]));
    }).catch(() => setSignals([]));
  }, [code]);

  if (signals.length === 0) {
    return <div className="card p-8 text-center text-sm text-gray-500">No escalated signal for this subsidiary yet — ripple effects appear once a signal is marked under evaluation on the Signal board.</div>;
  }

  return (
    <div className="space-y-6">
      {signals.map((s) => (
        <div key={s.id}>
          <h3 className="text-sm font-semibold text-gray-900 mb-2">{s.entity_name}</h3>
          {briefs[s.id] ? <EscalationBriefView brief={briefs[s.id]} entityName={s.entity_name} /> : <p className="text-xs text-gray-400">Loading escalation brief…</p>}
        </div>
      ))}
    </div>
  );
}

export default function AnalysisWorkspace() {
  const { company: encoded } = useParams<{ company: string }>();
  const company = decodeURIComponent(encoded || "");
  const app = useApp();
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>("swot");

  usePageMeta(`Deep dive · ${company}`, "Everything needed to decide — SWOT, dossier, research tools and ripple effect, in one place.");

  useEffect(() => {
    if (company) app.setScope(company);
  }, [company]);

  const code = CO_TO_CODE[company];

  if (!code) {
    return (
      <div className="card p-8 text-center">
        <p className="text-sm text-gray-500">Unknown subsidiary "{company}".</p>
        <button type="button" onClick={() => navigate("/dashboard")} className="btn btn-secondary btn-sm mt-3">Back to dashboard</button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-1.5 border-b border-gray-100 pb-3">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} type="button" onClick={() => setTab(key)}
            className={`inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full transition-colors ${
              tab === key ? "bg-zen-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      <div>
        {tab === "swot" && <Home />}
        {tab === "book" && <Book />}
        {tab === "follow" && <FollowUp />}
        {tab === "board" && <SignalBoardTab code={code} />}
        {tab === "ripple" && <RippleEffectTab code={code} />}
        {tab === "comp" && <Competitors />}
        {tab === "fin" && <Market />}
        {tab === "deals" && <RivalDeals />}
        {tab === "ask" && <AskRadar />}
        {tab === "thesis" && <Theses />}
        {tab === "trig" && <WatchRules />}
        {tab === "watched" && <Watched />}
      </div>
    </div>
  );
}

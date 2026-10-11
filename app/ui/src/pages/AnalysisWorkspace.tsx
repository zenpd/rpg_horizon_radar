import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle, Archive, BellRing, BookOpen, Briefcase, ClipboardCheck, Eye,
  Landmark, LayoutGrid, LineChart, MessageCircleQuestion, Share2, Target, Users,
} from "lucide-react";

import { usePageMeta } from "../context/PageMetaContext";
import { useApp } from "../radar/state";
import Home from "../radar/pages/Home";
import Book from "../radar/pages/Book";
import FollowUp from "../radar/pages/FollowUp";
import { AskRadar, Competitors, Market, RivalDeals } from "../radar/pages/Explore";
import { Theses, Watched, WatchRules } from "../radar/pages/Settings";
import { getCompanyProfile, getEscalationBrief, getSignals } from "../services/api";
import SignalCard from "../components/SignalCard";
import EscalationBriefView from "../components/EscalationBrief";
import ScoreBadge from "../components/ScoreBadge";
import type { CompanyProfile, EscalationBrief, SignalClusterSummary } from "../types";
import { CO_TO_CODE } from "../radar/companyCodes";

type TabKey = "swot" | "profile" | "book" | "follow" | "board" | "ripple" | "comp" | "fin" | "deals" | "ask" | "thesis" | "trig" | "watched";

const TABS: { key: TabKey; label: string; icon: typeof LayoutGrid }[] = [
  { key: "swot", label: "SWOT", icon: LayoutGrid },
  { key: "profile", label: "Company Profile", icon: Landmark },
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

function CompanyProfileCard({ profile }: { profile: CompanyProfile }) {
  const FIELDS: { label: string; value: string }[] = [
    { label: "Market reaction (heuristic, directional only)", value: profile.market_reaction },
    { label: "Brand / integration stance (heuristic)", value: profile.integration_stance },
    { label: "Likely deal structure (heuristic)", value: profile.deal_structure_hint },
    { label: "Regulatory note", value: profile.regulatory_note },
  ];
  return (
    <div className="p-5 space-y-4">
      <div>
        <span
          className={`text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 ${
            profile.listing_status === "public"
              ? "bg-blue-50 text-blue-700 ring-1 ring-blue-200"
              : "bg-gray-100 text-gray-600 ring-1 ring-gray-200"
          }`}
        >
          {profile.listing_label}
        </span>
        <p className="text-xs text-slate-500 leading-relaxed mt-1.5">{profile.listing_detail}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <div key={f.label} className="rounded-xl border border-gray-100 bg-gray-50/60 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-1">{f.label}</p>
            <p className="text-xs text-slate-700 leading-relaxed">{f.value}</p>
          </div>
        ))}
      </div>
      <div className="flex items-start gap-2 border-t border-amber-200 bg-amber-50 -mx-5 -mb-5 px-5 py-3 mt-2">
        <AlertTriangle size={14} className="text-amber-700 shrink-0 mt-0.5" />
        <p className="text-[11px] text-amber-700 leading-relaxed">{profile.disclaimer}</p>
      </div>
    </div>
  );
}

function CompanyProfileTab({ code }: { code: string }) {
  const [signals, setSignals] = useState<SignalClusterSummary[]>([]);
  const [profiles, setProfiles] = useState<Record<number, CompanyProfile>>({});

  useEffect(() => {
    Promise.all([
      getSignals({ subsidiary: code, status: "under_evaluation" }),
      getSignals({ subsidiary: code, status: "live" }),
    ]).then(async ([underEval, live]) => {
      const all = [...underEval, ...live];
      setSignals(all);
      const entries = await Promise.all(
        all.map(async (s) => [s.id, await getCompanyProfile(s.id).catch(() => null)] as const)
      );
      setProfiles(Object.fromEntries(entries.filter(([, p]) => p) as [number, CompanyProfile][]));
    }).catch(() => setSignals([]));
  }, [code]);

  if (signals.length === 0) {
    return (
      <div className="card p-8 text-center text-sm text-gray-500">
        No signals for this subsidiary yet — a company profile appears for every live or under-evaluation signal.
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {signals.map((s) => (
        <div key={s.id} className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">{s.entity_name}</h3>
              <p className="text-xs text-slate-500 mt-0.5">{s.entity_sectors.join(" · ") || "Sector not tagged"}</p>
            </div>
            <ScoreBadge score={s.score} />
          </div>
          {profiles[s.id] ? <CompanyProfileCard profile={profiles[s.id]} /> : <p className="text-xs text-gray-400 px-5 py-4">Loading…</p>}
        </div>
      ))}
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
        {tab === "profile" && <CompanyProfileTab code={code} />}
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

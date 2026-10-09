import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, AlertTriangle, ArrowRight, CalendarDays, Share2, TrendingUp } from "lucide-react";

import { usePageMeta } from "../context/PageMetaContext";
import { getDigests, getSignals } from "../services/api";
import { api as radarApi, type DigestSwot, type DigestSwotSubsidiary } from "../radar/api";
import type { DigestSummary, SignalClusterSummary } from "../types";

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function formatRange(start: string, end: string) {
  const fmt = (v: string) => new Date(v).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `${fmt(start)} – ${fmt(end)}`;
}

function KpiTile({ icon, chip, value, label, sub }: { icon: ReactNode; chip: string; value: number; label: string; sub?: string }) {
  return (
    <div className="card p-4 flex items-center gap-3">
      <div className={`w-10 h-10 rounded-xl ${chip} flex items-center justify-center flex-shrink-0`}>{icon}</div>
      <div>
        <p className="text-xl font-bold text-gray-900">{value}</p>
        <p className="text-xs text-gray-400">{label}</p>
        {sub && <p className="text-[10px] text-gray-300 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

function MiniSwotQuadrant({ title, accent, items }: { title: string; accent: string; items: { id: string; text: string }[] }) {
  return (
    <div className={`rounded-lg p-2.5 ${accent}`}>
      <p className="text-[10px] font-semibold uppercase tracking-wide mb-1 opacity-70">{title}</p>
      {items.length === 0 ? (
        <p className="text-[11px] opacity-50">—</p>
      ) : (
        <ul className="space-y-0.5">
          {items.slice(0, 2).map((x) => (
            <li key={x.id} className="text-[11px] leading-snug line-clamp-2">{x.text}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SubsidiarySwotCard({ sub }: { sub: DigestSwotSubsidiary }) {
  const navigate = useNavigate();
  return (
    <div className="card p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">{sub.co}</h3>
        <span className="text-xs bg-zen-50 text-zen-700 rounded-full px-2 py-0.5 font-medium">
          {sub.signal_count} signal{sub.signal_count === 1 ? "" : "s"}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <MiniSwotQuadrant title="Strengths" accent="bg-emerald-50 text-emerald-900" items={sub.swot.S} />
        <MiniSwotQuadrant title="Weaknesses" accent="bg-amber-50 text-amber-900" items={sub.swot.W} />
        <MiniSwotQuadrant title="Opportunities" accent="bg-blue-50 text-blue-900" items={sub.swot.O} />
        <MiniSwotQuadrant title="Threats" accent="bg-rose-50 text-rose-900" items={sub.swot.T} />
      </div>
      <button
        type="button"
        onClick={() => navigate(`/analyze/${encodeURIComponent(sub.co)}`)}
        className="btn btn-restricted btn-sm self-start mt-1"
      >
        Deep dive to analyze <ArrowRight size={13} />
      </button>
    </div>
  );
}

export default function ExecutiveDashboard() {
  usePageMeta("Executive Dashboard", "This week's M&A-potential signals, by subsidiary — with the SWOT behind each one.");

  const [digests, setDigests] = useState<DigestSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [data, setData] = useState<DigestSwot | null>(null);
  const [liveSignals, setLiveSignals] = useState<SignalClusterSummary[]>([]);
  const [underEval, setUnderEval] = useState<SignalClusterSummary[]>([]);
  const [year, setYear] = useState<string>("");
  const [month, setMonth] = useState<string>("");

  useEffect(() => {
    getDigests().then((list) => {
      setDigests(list);
      if (list.length) {
        const latest = list[0]; // API already orders newest-first
        const d = new Date(latest.period_end);
        setYear(String(d.getFullYear()));
        setMonth(String(d.getMonth()));
        setSelectedId(latest.id);
      }
    }).catch(() => undefined);
    getSignals({ status: "live" }).then(setLiveSignals).catch(() => undefined);
    getSignals({ status: "under_evaluation" }).then(setUnderEval).catch(() => undefined);
  }, []);

  useEffect(() => {
    radarApi.digestSwot(selectedId ?? undefined).then(setData).catch(() => undefined);
  }, [selectedId]);

  const years = useMemo(() => Array.from(new Set(digests.map((d) => new Date(d.period_end).getFullYear()))).sort((a, b) => b - a), [digests]);
  const monthsInYear = useMemo(
    () => Array.from(new Set(digests.filter((d) => String(new Date(d.period_end).getFullYear()) === year).map((d) => new Date(d.period_end).getMonth()))).sort((a, b) => a - b),
    [digests, year]
  );
  const weeksInMonth = useMemo(
    () => digests.filter((d) => {
      const dt = new Date(d.period_end);
      return String(dt.getFullYear()) === year && String(dt.getMonth()) === month;
    }),
    [digests, year, month]
  );

  const highSeverity = liveSignals.filter((s) => s.score >= 75).length;

  return (
    <div className="space-y-6">
      <div className="card p-4 flex flex-wrap items-center gap-3">
        <CalendarDays size={16} className="text-gray-400" />
        <span className="text-xs text-gray-500">Week of:</span>
        <select className="input !w-auto text-sm" value={year} onChange={(e) => { setYear(e.target.value); setMonth(""); }}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <select className="input !w-auto text-sm" value={month} onChange={(e) => setMonth(e.target.value)}>
          {monthsInYear.map((m) => <option key={m} value={m}>{MONTH_NAMES[m]}</option>)}
        </select>
        <select className="input !w-auto text-sm" value={selectedId ?? ""} onChange={(e) => setSelectedId(Number(e.target.value))}>
          {weeksInMonth.map((d) => <option key={d.id} value={d.id}>{formatRange(d.period_start, d.period_end)}</option>)}
        </select>
        {digests.length === 0 && <span className="text-xs text-gray-400">No digests generated yet.</span>}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile icon={<TrendingUp size={18} className="text-zen-600" />} chip="bg-zen-50" value={data?.subsidiaries.length ?? 0} label="Subsidiaries with signals" sub="selected week" />
        <KpiTile icon={<Activity size={18} className="text-blue-500" />} chip="bg-blue-50" value={data?.subsidiaries.reduce((a, s) => a + s.signal_count, 0) ?? 0} label="Signals in this digest" sub="selected week" />
        <KpiTile icon={<AlertTriangle size={18} className="text-rose-500" />} chip="bg-rose-50" value={highSeverity} label="High severity" sub="live, right now" />
        <KpiTile icon={<Share2 size={18} className="text-violet-500" />} chip="bg-violet-50" value={underEval.length} label="Escalations under evaluation" sub="right now" />
      </div>

      {data && data.subsidiaries.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {data.subsidiaries.map((sub) => <SubsidiarySwotCard key={sub.co} sub={sub} />)}
        </div>
      ) : (
        <div className="card p-8 text-center">
          <p className="text-sm text-gray-500">
            {digests.length === 0
              ? "No digest has been generated yet — once the weekly scan runs, M&A-potential signals will show up here by subsidiary."
              : "No subsidiary had an M&A-potential signal strong enough to reach this week's digest."}
          </p>
        </div>
      )}
    </div>
  );
}

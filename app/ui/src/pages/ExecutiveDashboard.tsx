import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, AlertTriangle, ArrowRight, CalendarDays, ChevronRight, Share2, TrendingUp } from "lucide-react";

import { usePageMeta } from "../context/PageMetaContext";
import { getDigest, getDigests, getSignals } from "../services/api";
import { api as radarApi, type DigestSwot, type DigestSwotSubsidiary, type SwotItem } from "../radar/api";
import { CODE_TO_CO } from "../radar/companyCodes";
import type { DigestDetail, DigestSummary, SignalClusterSummary } from "../types";
import WeeklyTrendChart from "../components/WeeklyTrendChart";
import SeverityDonut, { type SeverityCounts } from "../components/SeverityDonut";
import SwotRadarChart, { type SwotCounts } from "../components/SwotRadarChart";
import DetailDrawer from "../components/DetailDrawer";
import ScoreBadge from "../components/ScoreBadge";

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const SUBSIDIARY_COUNT = Object.keys(CODE_TO_CO).length;

const QUADRANT_LABEL: Record<keyof SwotCounts, string> = { S: "Strengths", O: "Opportunities", W: "Weaknesses", T: "Threats" };

type Drawer =
  | { kind: "subsidiaries" }
  | { kind: "digest-items" }
  | { kind: "severity"; band: keyof SeverityCounts }
  | { kind: "under-eval" }
  | { kind: "swot-item"; co: string; quadrant: keyof SwotCounts; items: SwotItem[] };

function formatRange(start: string, end: string) {
  const fmt = (v: string) => new Date(v).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `${fmt(start)} – ${fmt(end)}`;
}

function KpiTile({ icon, chip, value, label, sub, onClick }: { icon: ReactNode; chip: string; value: number; label: string; sub?: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className="card p-4 flex items-center gap-3 text-left w-full disabled:cursor-default enabled:hover:shadow-card-hover enabled:hover:-translate-y-0.5 transition-all duration-150"
    >
      <div className={`w-10 h-10 rounded-xl ${chip} flex items-center justify-center flex-shrink-0`}>{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-xl font-bold text-gray-900">{value}</p>
        <p className="text-xs text-gray-400">{label}</p>
        {sub && <p className="text-[10px] text-gray-300 mt-0.5">{sub}</p>}
      </div>
      {onClick && <ChevronRight size={15} className="text-gray-300 flex-shrink-0" />}
    </button>
  );
}

function MiniSwotQuadrant({ title, accent, items, onOpen }: { title: string; accent: string; items: { id: string; text: string }[]; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={items.length === 0}
      className={`rounded-lg p-2.5 text-left w-full ${accent} disabled:cursor-default enabled:hover:ring-2 enabled:hover:ring-inset enabled:ring-current/20 transition-shadow`}
    >
      <p className="text-[10px] font-semibold uppercase tracking-wide mb-1 opacity-70">{title}</p>
      {items.length === 0 ? (
        <p className="text-[11px] opacity-50">—</p>
      ) : (
        <>
          <ul className="space-y-0.5">
            {items.slice(0, 2).map((x) => (
              <li key={x.id} className="text-[11px] leading-snug line-clamp-2">{x.text}</li>
            ))}
          </ul>
          {items.length > 2 && <p className="text-[10px] font-semibold opacity-60 mt-1">+{items.length - 2} more — click for detail &amp; sources</p>}
          {items.length <= 2 && <p className="text-[10px] font-semibold opacity-40 mt-1">click for reasoning &amp; sources</p>}
        </>
      )}
    </button>
  );
}

function SubsidiarySwotCard({ sub, onOpenQuadrant }: { sub: DigestSwotSubsidiary; onOpenQuadrant: (co: string, quadrant: keyof SwotCounts, items: SwotItem[]) => void }) {
  const navigate = useNavigate();
  const counts: SwotCounts = { S: sub.swot.S.length, O: sub.swot.O.length, W: sub.swot.W.length, T: sub.swot.T.length };
  return (
    <div className="card p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">{sub.co}</h3>
        <span className="text-xs bg-zen-50 text-zen-700 rounded-full px-2 py-0.5 font-medium">
          {sub.signal_count} signal{sub.signal_count === 1 ? "" : "s"}
        </span>
      </div>
      <div className="flex gap-3 items-center">
        <SwotRadarChart counts={counts} onAxisClick={(q) => onOpenQuadrant(sub.co, q, sub.swot[q])} />
        <div className="grid grid-cols-2 gap-2 flex-1">
          <MiniSwotQuadrant title="Strengths" accent="bg-emerald-50 text-emerald-900" items={sub.swot.S} onOpen={() => onOpenQuadrant(sub.co, "S", sub.swot.S)} />
          <MiniSwotQuadrant title="Weaknesses" accent="bg-amber-50 text-amber-900" items={sub.swot.W} onOpen={() => onOpenQuadrant(sub.co, "W", sub.swot.W)} />
          <MiniSwotQuadrant title="Opportunities" accent="bg-blue-50 text-blue-900" items={sub.swot.O} onOpen={() => onOpenQuadrant(sub.co, "O", sub.swot.O)} />
          <MiniSwotQuadrant title="Threats" accent="bg-rose-50 text-rose-900" items={sub.swot.T} onOpen={() => onOpenQuadrant(sub.co, "T", sub.swot.T)} />
        </div>
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

function SignalRow({ cluster }: { cluster: SignalClusterSummary }) {
  const navigate = useNavigate();
  const co = cluster.subsidiaries.map((s) => CODE_TO_CO[s]).find(Boolean);
  return (
    <div className="rounded-xl border border-gray-100 bg-gray-50/60 p-3 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-slate-800">{cluster.entity_name}</p>
        <ScoreBadge score={cluster.score} />
      </div>
      <p className="text-xs text-gray-500 leading-relaxed">{cluster.rationale}</p>
      <div className="flex items-center justify-between pt-0.5 gap-2">
        <div className="flex flex-wrap gap-1">
          {cluster.subsidiaries.map((s) => (
            <span key={s} className="text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 bg-zen-50 text-zen-700 ring-1 ring-zen-200">{s}</span>
          ))}
        </div>
        {co && (
          <button type="button" onClick={() => navigate(`/analyze/${encodeURIComponent(co)}`)} className="text-xs font-semibold text-zen-700 hover:underline flex items-center gap-1 flex-shrink-0">
            Deep dive <ArrowRight size={11} />
          </button>
        )}
      </div>
    </div>
  );
}

export default function ExecutiveDashboard() {
  usePageMeta("Executive Dashboard", "This week's M&A-potential signals, by subsidiary — with the SWOT behind each one.");
  const navigate = useNavigate();

  const [digests, setDigests] = useState<DigestSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [data, setData] = useState<DigestSwot | null>(null);
  const [liveSignals, setLiveSignals] = useState<SignalClusterSummary[]>([]);
  const [underEval, setUnderEval] = useState<SignalClusterSummary[]>([]);
  const [year, setYear] = useState<string>("");
  const [month, setMonth] = useState<string>("");
  const [drawer, setDrawer] = useState<Drawer | null>(null);
  const [digestDetail, setDigestDetail] = useState<DigestDetail | null>(null);
  const [digestDetailLoading, setDigestDetailLoading] = useState(false);

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
    setDigestDetail(null);
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

  // Keep the three cascading dropdowns self-consistent: whenever the year
  // changes (or the current month no longer exists in it), fall back to the
  // most recent month in that year — same idea one level down for the week.
  useEffect(() => {
    if (monthsInYear.length && (month === "" || !monthsInYear.includes(Number(month)))) {
      setMonth(String(monthsInYear[monthsInYear.length - 1]));
    }
  }, [monthsInYear]);
  useEffect(() => {
    if (weeksInMonth.length && !weeksInMonth.some((d) => d.id === selectedId)) {
      setSelectedId(weeksInMonth[0].id);
    }
  }, [weeksInMonth]);

  const jumpToWeek = (id: number) => {
    const d = digests.find((x) => x.id === id);
    if (!d) return;
    const dt = new Date(d.period_end);
    setYear(String(dt.getFullYear()));
    setMonth(String(dt.getMonth()));
    setSelectedId(id);
  };

  const highSeverity = liveSignals.filter((s) => s.score >= 75).length;

  const trendPoints = useMemo(
    () => [...digests]
      .sort((a, b) => new Date(a.period_end).getTime() - new Date(b.period_end).getTime())
      .map((d) => ({
        label: new Date(d.period_end).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        value: Object.values(d.subsidiary_breakdown).reduce((a, b) => a + b, 0),
        highlighted: d.id === selectedId,
        id: d.id,
      })),
    [digests, selectedId]
  );

  const severityCounts: SeverityCounts = useMemo(() => ({
    low: liveSignals.filter((s) => s.score < 50).length,
    elevated: liveSignals.filter((s) => s.score >= 50 && s.score < 75).length,
    high: liveSignals.filter((s) => s.score >= 75).length,
  }), [liveSignals]);

  const openDigestItems = () => {
    setDrawer({ kind: "digest-items" });
    if (selectedId != null && !digestDetail) {
      setDigestDetailLoading(true);
      getDigest(selectedId).then(setDigestDetail).catch(() => undefined).finally(() => setDigestDetailLoading(false));
    }
  };

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
        <KpiTile
          icon={<TrendingUp size={18} className="text-zen-600" />} chip="bg-zen-50"
          value={data?.subsidiaries.length ?? 0} label="Subsidiaries with signals"
          sub={`of ${SUBSIDIARY_COUNT} · selected week`}
          onClick={() => setDrawer({ kind: "subsidiaries" })}
        />
        <KpiTile
          icon={<Activity size={18} className="text-blue-500" />} chip="bg-blue-50"
          value={data?.subsidiaries.reduce((a, s) => a + s.signal_count, 0) ?? 0} label="Signals in this digest"
          sub="score ≥65 · selected week"
          onClick={openDigestItems}
        />
        <KpiTile
          icon={<AlertTriangle size={18} className="text-rose-500" />} chip="bg-rose-50"
          value={highSeverity} label="High severity"
          sub="score ≥75 · live right now"
          onClick={() => setDrawer({ kind: "severity", band: "high" })}
        />
        <KpiTile
          icon={<Share2 size={18} className="text-violet-500" />} chip="bg-violet-50"
          value={underEval.length} label="Escalations under evaluation"
          sub="flagged by a reviewer · now"
          onClick={() => setDrawer({ kind: "under-eval" })}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <h2 className="font-semibold text-gray-900 mb-1 text-sm">Signal volume by week</h2>
          <p className="text-[11px] text-gray-400 mb-2">Total digest-worthy signals per week · click a bar to jump there</p>
          <WeeklyTrendChart points={trendPoints} onSelect={jumpToWeek} />
        </div>
        <div className="card p-5">
          <h2 className="font-semibold text-gray-900 mb-1 text-sm">Live signals by severity</h2>
          <p className="text-[11px] text-gray-400 mb-2">All signals currently live · click a band for the list</p>
          <SeverityDonut counts={severityCounts} onSelect={(band) => setDrawer({ kind: "severity", band })} />
        </div>
      </div>

      {data && data.subsidiaries.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {data.subsidiaries.map((sub) => (
            <SubsidiarySwotCard
              key={sub.co}
              sub={sub}
              onOpenQuadrant={(co, quadrant, items) => setDrawer({ kind: "swot-item", co, quadrant, items })}
            />
          ))}
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

      <DetailDrawer
        open={drawer?.kind === "subsidiaries"}
        onClose={() => setDrawer(null)}
        title="Subsidiaries with a signal this week"
        basis={`Out of ${SUBSIDIARY_COUNT} tracked subsidiaries, these had at least one cluster scoring ≥65 in the selected digest.`}
      >
        <div className="space-y-2">
          {(data?.subsidiaries ?? []).map((sub) => (
            <button
              key={sub.co}
              type="button"
              onClick={() => navigate(`/analyze/${encodeURIComponent(sub.co)}`)}
              className="w-full flex items-center justify-between rounded-xl border border-gray-100 bg-gray-50/60 p-3 hover:bg-gray-100 text-left transition-colors"
            >
              <div>
                <p className="text-sm font-semibold text-slate-800">{sub.co}</p>
                <p className="text-xs text-gray-500">{sub.signal_count} signal{sub.signal_count === 1 ? "" : "s"} this week</p>
              </div>
              <ArrowRight size={14} className="text-gray-400" />
            </button>
          ))}
        </div>
      </DetailDrawer>

      <DetailDrawer
        open={drawer?.kind === "digest-items"}
        onClose={() => setDrawer(null)}
        title="Signals in this digest"
        basis="Every signal cluster included in the selected week's digest — the exact rows the count above adds up."
      >
        {digestDetailLoading && <p className="text-xs text-gray-400">Loading…</p>}
        {!digestDetailLoading && (!digestDetail || digestDetail.items.length === 0) && (
          <p className="text-xs text-gray-400">No items in this digest.</p>
        )}
        <div className="space-y-2">
          {digestDetail?.items.map((item, i) => <SignalRow key={i} cluster={item.cluster} />)}
        </div>
      </DetailDrawer>

      {drawer?.kind === "severity" && (
        <DetailDrawer
          open
          onClose={() => setDrawer(null)}
          title={`${drawer.band[0].toUpperCase()}${drawer.band.slice(1)} severity — live signals`}
          basis={`Live signals with ${drawer.band === "high" ? "score ≥75" : drawer.band === "elevated" ? "score 50–74" : "score <50"} — same thresholds as the score badges everywhere else in the app.`}
        >
          <div className="space-y-2">
            {liveSignals
              .filter((s) => (drawer.band === "high" ? s.score >= 75 : drawer.band === "elevated" ? s.score >= 50 && s.score < 75 : s.score < 50))
              .sort((a, b) => b.score - a.score)
              .map((s) => <SignalRow key={s.id} cluster={s} />)}
          </div>
        </DetailDrawer>
      )}

      <DetailDrawer
        open={drawer?.kind === "under-eval"}
        onClose={() => setDrawer(null)}
        title="Escalations under evaluation"
        basis="Signals a named reviewer has flagged for active evaluation, with an Escalation Brief now available on the Ripple Effect tab."
      >
        <div className="space-y-2">
          {underEval.length === 0 && <p className="text-xs text-gray-400">Nothing under evaluation right now.</p>}
          {underEval.map((s) => <SignalRow key={s.id} cluster={s} />)}
        </div>
      </DetailDrawer>

      {drawer?.kind === "swot-item" && (
        <DetailDrawer
          open
          onClose={() => setDrawer(null)}
          title={`${drawer.co} — ${QUADRANT_LABEL[drawer.quadrant]}`}
          basis="Each item below is evidence-cited: the reasoning and sources are exactly what the SWOT was built from, nothing inferred beyond it."
        >
          <div className="space-y-3">
            {drawer.items.length === 0 && <p className="text-xs text-gray-400">No evidenced items in this quadrant for this subsidiary.</p>}
            {drawer.items.map((item) => (
              <div key={item.id} className="rounded-xl border border-gray-100 bg-gray-50/60 p-3 space-y-1.5">
                <p className="text-sm text-slate-800 leading-relaxed">{item.text}</p>
                {item.reasoning && <p className="text-xs text-gray-500 leading-relaxed italic">{item.reasoning}</p>}
                {item.sources.length > 0 && (
                  <div className="pt-1 space-y-1 border-t border-gray-100 mt-1.5">
                    {item.sources.map((src) => (
                      <div key={src.id} className="text-[11px] text-gray-500 flex items-center gap-1.5 flex-wrap">
                        <span className="font-semibold text-gray-600">{src.origin_label}</span>
                        <span>·</span>
                        {src.url ? (
                          <a href={src.url} target="_blank" rel="noreferrer" className="text-zen-700 hover:underline truncate">{src.source}</a>
                        ) : (
                          <span>{src.source}</span>
                        )}
                        {src.date && <span className="text-gray-400">· {new Date(src.date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </DetailDrawer>
      )}
    </div>
  );
}

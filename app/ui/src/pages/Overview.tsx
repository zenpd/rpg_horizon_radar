import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, AlertTriangle, ArrowRight, Share2, TrendingUp } from "lucide-react";

import { usePageMeta } from "../context/PageMetaContext";
import { getDigests, getEscalationBrief, getSignals } from "../services/api";
import { api as radarApi } from "../radar/api";
import type { DigestSummary, EscalationBrief, SignalClusterSummary } from "../types";

function formatDate(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return value;
  }
}

const DEPENDENCY_LABEL: Record<string, string> = {
  raw_material: "Raw material",
  byproduct: "Byproduct",
  shared_service: "Shared service",
  shared_vendor: "Shared vendor",
};

function KpiTile({ icon, chip, value, label }: { icon: ReactNode; chip: string; value: number; label: string }) {
  return (
    <div className="card p-4 flex items-center gap-3">
      <div className={`w-10 h-10 rounded-xl ${chip} flex items-center justify-center flex-shrink-0`}>{icon}</div>
      <div>
        <p className="text-xl font-bold text-gray-900">{value}</p>
        <p className="text-xs text-gray-400">{label}</p>
      </div>
    </div>
  );
}

function PillarCard({ title, children, linkTo, linkLabel }: { title: string; children: ReactNode; linkTo: string; linkLabel: string }) {
  const navigate = useNavigate();
  return (
    <div className="card p-5 flex flex-col gap-3">
      <h2 className="font-semibold text-gray-900">{title}</h2>
      <div className="flex-1 text-sm text-gray-600 space-y-2">{children}</div>
      <button type="button" onClick={() => navigate(linkTo)} className="btn btn-secondary btn-sm self-start">
        {linkLabel} <ArrowRight size={13} />
      </button>
    </div>
  );
}

export default function Overview() {
  usePageMeta("Executive Overview", "This week's weekly digest, post-acquisition SWOT, and ripple effect — at a glance.");

  const [digests, setDigests] = useState<DigestSummary[]>([]);
  const [liveSignals, setLiveSignals] = useState<SignalClusterSummary[]>([]);
  const [underEval, setUnderEval] = useState<SignalClusterSummary[]>([]);
  const [latestBrief, setLatestBrief] = useState<EscalationBrief | null>(null);
  const [approvedDeals, setApprovedDeals] = useState<{ id: string; title: string; who: string }[]>([]);

  useEffect(() => {
    getDigests().then(setDigests).catch(() => undefined);
    getSignals({ status: "live" }).then(setLiveSignals).catch(() => undefined);
    getSignals({ status: "under_evaluation" }).then(async (signals) => {
      setUnderEval(signals);
      if (signals.length) {
        try {
          setLatestBrief(await getEscalationBrief(signals[0].id));
        } catch {
          setLatestBrief(null);
        }
      }
    }).catch(() => undefined);
    radarApi.book().then((b) => {
      setApprovedDeals(
        b.pages
          .filter((p) => p.kind === "deal" && (p.stage === "act" || p.stage === "closed"))
          .map((p) => ({ id: p.id, title: p.title, who: p.who }))
      );
    }).catch(() => undefined);
  }, []);

  const latestDigest = digests[0];
  const signalsThisWeek = latestDigest ? Object.values(latestDigest.subsidiary_breakdown).reduce((a, b) => a + b, 0) : 0;
  const highSeverity = liveSignals.filter((s) => s.score >= 75).length;
  const latestUnderEval = underEval[0];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiTile icon={<Activity size={18} className="text-blue-500" />} chip="bg-blue-50" value={signalsThisWeek} label="Signals this week" />
        <KpiTile icon={<TrendingUp size={18} className="text-zen-600" />} chip="bg-zen-50" value={approvedDeals.length} label="Acquisitions evaluated" />
        <KpiTile icon={<Share2 size={18} className="text-violet-500" />} chip="bg-violet-50" value={underEval.length} label="Escalations (ripple surfaced)" />
        <KpiTile icon={<AlertTriangle size={18} className="text-rose-500" />} chip="bg-rose-50" value={highSeverity} label="High severity signals" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <PillarCard title="Weekly Digest" linkTo="/digests" linkLabel="Open Digest archive">
          {latestDigest ? (
            <>
              <p>{formatDate(latestDigest.period_start)} – {formatDate(latestDigest.period_end)}</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(latestDigest.subsidiary_breakdown).map(([code, count]) => (
                  <span key={code} className="text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">{code}: {count}</span>
                ))}
              </div>
            </>
          ) : (
            <p className="text-gray-400">No digest generated yet.</p>
          )}
        </PillarCard>

        <PillarCard title="Post-Acquisition SWOT" linkTo="/" linkLabel="Open Deep-dive book">
          {approvedDeals.length ? (
            <>
              <p>{approvedDeals.length} acquisition{approvedDeals.length === 1 ? "" : "s"} approved, most recently <b>{approvedDeals[approvedDeals.length - 1].who}</b>.</p>
              <p className="text-xs text-gray-400">Each approved deal's book page shows its projected post-acquisition SWOT shift.</p>
            </>
          ) : (
            <p className="text-gray-400">No acquisitions approved yet.</p>
          )}
        </PillarCard>

        <PillarCard title="Ripple Effect" linkTo="/board" linkLabel="Open Signal board">
          {latestBrief && latestBrief.ripple_effects.length ? (
            <>
              <p>From escalating <b>{latestUnderEval?.entity_name}</b>:</p>
              {latestBrief.ripple_effects.slice(0, 3).map((r, i) => (
                <div key={i} className="flex items-start gap-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wide bg-gray-100 text-gray-600 rounded-full px-2 py-0.5 shrink-0">
                    {DEPENDENCY_LABEL[r.dependency_type] ?? r.dependency_type}
                  </span>
                  <span className="text-xs">{r.counterparty_name}</span>
                </div>
              ))}
            </>
          ) : (
            <p className="text-gray-400">No signal under evaluation yet.</p>
          )}
        </PillarCard>
      </div>
    </div>
  );
}

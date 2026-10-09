import { useNavigate } from "react-router-dom";

import ScoreBadge from "./ScoreBadge";
import type { SignalClusterSummary } from "../types";

const STATUS_LABEL: Record<string, string> = {
  live: "Live",
  under_evaluation: "Under Active Evaluation",
};

interface SignalCardProps {
  signal: SignalClusterSummary;
  compact?: boolean;
}

export default function SignalCard({ signal, compact = false }: SignalCardProps) {
  const navigate = useNavigate();

  const rationale = signal.rationale || "";
  const truncated =
    rationale.length > 160 && !compact ? `${rationale.slice(0, 160).trimEnd()}…` : rationale;

  const statusBadge = (
    <span className={signal.status === "under_evaluation" ? "status-under_evaluation" : "status-live"}>
      {STATUS_LABEL[signal.status] || signal.status}
    </span>
  );

  // Compact mode is used inline in a list (digest detail) — render as a plain
  // row meant to sit inside an outer `.card overflow-hidden divide-y` list,
  // matching digital-onboarding's Recent-Sessions row pattern rather than
  // nesting a card inside a card.
  if (compact) {
    return (
      <button
        type="button"
        onClick={() => navigate(`/signals/${signal.id}`)}
        className="w-full flex items-center gap-3 px-5 py-3.5 text-left hover:bg-gray-50/80 transition-colors group"
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-800 truncate group-hover:text-zen-700 transition-colors">
            {signal.entity_name}
          </p>
          <div className="flex flex-wrap items-center gap-1.5 mt-1">
            {(signal.signal_types || []).map((t) => (
              <span
                key={t}
                className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-600"
              >
                {t.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
        {statusBadge}
        <ScoreBadge score={signal.score} />
      </button>
    );
  }

  return (
    <button type="button" onClick={() => navigate(`/signals/${signal.id}`)} className="w-full text-left p-4 card-hover">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-slate-900 truncate text-base">{signal.entity_name}</p>
          {Array.isArray(signal.entity_sectors) && signal.entity_sectors.length > 0 && (
            <p className="text-xs text-slate-500 mt-0.5">{signal.entity_sectors.join(" · ")}</p>
          )}
        </div>
        <ScoreBadge score={signal.score} />
      </div>

      {rationale && <p className="text-sm text-slate-600 mt-2.5 leading-relaxed">{truncated}</p>}

      <div className="flex flex-wrap items-center gap-1.5 mt-3">
        {(signal.signal_types || []).map((t) => (
          <span
            key={t}
            className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-600"
          >
            {t.replace(/_/g, " ")}
          </span>
        ))}
        <span className="ml-auto">{statusBadge}</span>
      </div>
    </button>
  );
}

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

  return (
    <button
      type="button"
      onClick={() => navigate(`/signals/${signal.id}`)}
      className={`w-full text-left rounded-lg border border-ink-600 bg-ink-800 hover:border-accent/50 hover:bg-ink-700/60 transition-colors ${
        compact ? "px-3 py-2.5" : "p-4"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={`font-semibold text-ink-100 truncate ${compact ? "text-sm" : "text-base"}`}>
            {signal.entity_name}
          </p>
          {!compact && Array.isArray(signal.entity_sectors) && signal.entity_sectors.length > 0 && (
            <p className="text-xs text-ink-500 mt-0.5">{signal.entity_sectors.join(" · ")}</p>
          )}
        </div>
        <ScoreBadge score={signal.score} />
      </div>

      {!compact && rationale && (
        <p className="text-sm text-ink-300 mt-2.5 leading-relaxed">{truncated}</p>
      )}

      <div className="flex flex-wrap items-center gap-1.5 mt-3">
        {(signal.signal_types || []).map((t) => (
          <span
            key={t}
            className="rounded border border-ink-600 bg-ink-900 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-500"
          >
            {t.replace(/_/g, " ")}
          </span>
        ))}
        <span
          className={`ml-auto rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
            signal.status === "under_evaluation"
              ? "bg-accent/15 text-accent-light"
              : "bg-ink-700 text-ink-400"
          }`}
        >
          {STATUS_LABEL[signal.status] || signal.status}
        </span>
      </div>
    </button>
  );
}

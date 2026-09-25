import toast from "react-hot-toast";
import { AlertTriangle, Clipboard, ThumbsDown, ThumbsUp } from "lucide-react";

import type { EscalationBrief as EscalationBriefType } from "../types";

function asPlainText(brief: EscalationBriefType, entityName?: string) {
  const lines = [
    `ESCALATION BRIEF — ${entityName}`,
    `Deal complexity (heuristic): ${brief.deal_complexity}`,
    brief.escalated_by ? `Escalated by: ${brief.escalated_by}` : null,
    "",
    "PROS",
    ...brief.pros.map((p) => `  - ${p}`),
    "",
    "CONS / RISKS",
    ...brief.cons.map((c) => `  - ${c}`),
    "",
    "DIRECTIONAL CONSIDERATIONS (illustrative, not a valuation)",
    ...brief.directional_considerations.map((d) => `  - ${d.label}: ${d.value}`),
    "",
    brief.disclaimer,
  ].filter((l): l is string => l !== null);
  return lines.join("\n");
}

interface EscalationBriefProps {
  brief: EscalationBriefType | null;
  entityName?: string;
}

export default function EscalationBrief({ brief, entityName }: EscalationBriefProps) {
  if (!brief) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(asPlainText(brief, entityName));
      toast.success("Escalation brief copied as plain text.");
    } catch {
      toast.error("Couldn't copy to clipboard.");
    }
  };

  return (
    <div className="rounded-lg border border-accent/30 bg-ink-800">
      <div className="flex items-center justify-between border-b border-accent/20 px-5 py-3">
        <div>
          <h2 className="text-sm font-semibold text-ink-100">Escalation Brief</h2>
          <p className="text-[11px] text-ink-500 mt-0.5">
            Generated at hand-off · deal complexity: <span className="font-medium text-ink-300">{brief.deal_complexity}</span>
          </p>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md border border-ink-600 bg-ink-900 px-2.5 py-1.5 text-xs font-medium text-ink-300 hover:border-ink-500"
        >
          <Clipboard size={12} />
          Copy as text
        </button>
      </div>

      <div className="grid gap-4 p-5 sm:grid-cols-2">
        <div>
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-severity-low mb-2">
            <ThumbsUp size={12} /> Pros
          </p>
          <ul className="space-y-1.5">
            {brief.pros.map((p, i) => (
              <li key={i} className="text-xs text-ink-300 leading-relaxed">
                • {p}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-severity-high mb-2">
            <ThumbsDown size={12} /> Cons / Risks
          </p>
          <ul className="space-y-1.5">
            {brief.cons.map((c, i) => (
              <li key={i} className="text-xs text-ink-300 leading-relaxed">
                • {c}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="border-t border-ink-700 px-5 py-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500 mb-2">
          Directional considerations <span className="normal-case text-ink-600">(illustrative, not a valuation)</span>
        </p>
        <dl className="grid gap-2 sm:grid-cols-2">
          {brief.directional_considerations.map((d, i) => (
            <div key={i} className="rounded border border-ink-700 bg-ink-900 px-3 py-2">
              <dt className="text-[10px] uppercase tracking-wide text-ink-500">{d.label}</dt>
              <dd className="text-xs text-ink-200 mt-0.5">{d.value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="flex items-start gap-2 border-t border-ink-700 bg-ink-900/60 px-5 py-3 rounded-b-lg">
        <AlertTriangle size={14} className="text-severity-mid shrink-0 mt-0.5" />
        <p className="text-[11px] text-ink-400 leading-relaxed">{brief.disclaimer}</p>
      </div>
    </div>
  );
}

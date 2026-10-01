import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import toast from "react-hot-toast";
import axios from "axios";
import {
  ArrowLeft,
  Briefcase,
  FileText,
  Gavel,
  Newspaper,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { usePageMeta } from "../context/PageMetaContext";
import { getEscalationBrief, getSignal, markUnderEvaluation } from "../services/api";
import ScoreBadge from "../components/ScoreBadge";
import ConfirmModal from "../components/ConfirmModal";
import EscalationBrief from "../components/EscalationBrief";
import type {
  EscalationBrief as EscalationBriefType,
  SignalClusterDetail,
} from "../types";

// Distinct color per raw-signal source_type, matching digital-onboarding's
// AuditTrailPage icon-in-colored-box convention.
const SOURCE_CONFIG: Record<string, { icon: LucideIcon; bg: string; text: string; border: string }> = {
  news: { icon: Newspaper, bg: "bg-blue-50", text: "text-blue-600", border: "border-blue-100" },
  filings: { icon: FileText, bg: "bg-purple-50", text: "text-purple-600", border: "border-purple-100" },
  patents: { icon: Gavel, bg: "bg-teal-50", text: "text-teal-600", border: "border-teal-100" },
  hiring: { icon: Briefcase, bg: "bg-amber-50", text: "text-amber-600", border: "border-amber-100" },
};

function configFor(sourceType: string | undefined) {
  const key = (sourceType || "").toLowerCase();
  for (const prefix of Object.keys(SOURCE_CONFIG)) {
    if (key.includes(prefix)) return SOURCE_CONFIG[prefix];
  }
  return { icon: FileText, bg: "bg-gray-100", text: "text-gray-500", border: "border-gray-200" };
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

export default function SignalDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();

  const [signal, setSignal] = useState<SignalClusterDetail | null>(null);
  const [brief, setBrief] = useState<EscalationBriefType | null>(null);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  usePageMeta(
    signal ? signal.entity_name : "Signal Detail",
    signal ? `Routed → ${(signal.subsidiaries || []).join(", ") || "—"}` : undefined
  );

  const loadBriefIfEscalated = useCallback(async (sig: SignalClusterDetail | null) => {
    if (sig?.status !== "under_evaluation") return;
    try {
      const briefData = await getEscalationBrief(sig.id);
      setBrief(briefData);
    } catch {
      // Older signals escalated before this feature existed may have no
      // brief on record — fail quietly rather than blocking the page.
    }
  }, []);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getSignal(id);
      setSignal(data);
      await loadBriefIfEscalated(data);
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        toast.error("Signal not found.");
        navigate("/board", { replace: true });
      }
    } finally {
      setLoading(false);
    }
  }, [id, navigate, loadBriefIfEscalated]);

  useEffect(() => {
    load();
  }, [load]);

  const handleConfirmEvaluation = async () => {
    if (!id) return;
    setSubmitting(true);
    try {
      const updated = await markUnderEvaluation(id);
      setSignal(updated);
      toast.success("Signal marked under active evaluation and handed off to the formal M&A process.");
      setModalOpen(false);
      await loadBriefIfEscalated(updated);
    } catch {
      // handled globally
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="text-sm text-gray-400 py-10 text-center">Loading signal…</div>;
  }

  if (!signal) {
    return null;
  }

  const rawSignals = signal.raw_signals || [];

  return (
    <div className="space-y-6 max-w-4xl">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-xs font-medium text-gray-400 hover:text-gray-700"
      >
        <ArrowLeft size={14} />
        Back
      </button>

      <div className="card p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">{signal.entity_name}</h1>
            <p className="text-xs text-gray-400 mt-1">
              {(signal.entity_sectors || []).join(" · ")}
              {signal.entity_category ? ` — ${signal.entity_category}` : ""}
            </p>
            <div className="flex flex-wrap items-center gap-1.5 mt-3">
              {(signal.subsidiaries || []).map((code) => (
                <span key={code} className="rounded-full bg-gray-100 px-2.5 py-0.5 text-[10px] font-semibold text-gray-500">
                  Routed → {code}
                </span>
              ))}
            </div>
          </div>
          <ScoreBadge score={signal.score} size="lg" />
        </div>

        <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50/60 p-4">
          <p className="section-title mb-1.5">Rationale</p>
          <p className="text-sm text-gray-600 leading-relaxed">{signal.rationale}</p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 mt-4">
          {(signal.signal_types || []).map((t) => (
            <span
              key={t}
              className="rounded-full bg-gray-100 px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-500"
            >
              {t.replace(/_/g, " ")}
            </span>
          ))}
          <span className="ml-auto">
            <span className={signal.status === "under_evaluation" ? "status-under_evaluation" : "status-live"}>
              {signal.status === "under_evaluation" ? "Under Active Evaluation" : "Live"}
            </span>
          </span>
        </div>

        {signal.status === "under_evaluation" && (
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5">
            <ShieldCheck size={16} className="text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700 leading-relaxed">
              This signal has exited the AI system. It was handed off to the formal M&A process
              {signal.evaluated_by ? ` by ${signal.evaluated_by}` : ""}
              {signal.evaluated_at ? ` on ${formatDate(signal.evaluated_at)}` : ""}. This action cannot
              be undone from here.
            </p>
          </div>
        )}

        {isAdmin && signal.status === "live" && (
          <div className="mt-5 flex justify-end">
            <button type="button" onClick={() => setModalOpen(true)} className="btn btn-danger btn-sm">
              Mark Under Active Evaluation
            </button>
          </div>
        )}
      </div>

      {signal.status === "under_evaluation" && <EscalationBrief brief={brief} entityName={signal.entity_name} />}

      <div>
        <h2 className="section-title">Contributing Raw Signals</h2>
        <div className="card overflow-hidden divide-y divide-gray-50">
          {rawSignals.map((rs, idx) => {
            const cfg = configFor(rs.source_type);
            const Icon = cfg.icon;
            return (
              <div key={idx} className="flex items-start gap-4 px-5 py-3.5">
                <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 border ${cfg.bg} ${cfg.border}`}>
                  <Icon size={14} className={cfg.text} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wide text-gray-400">
                      {rs.signal_type?.replace(/_/g, " ")} · {rs.source_type?.replace(/_/g, " ")}
                      {rs.provider && rs.provider !== "mock" ? ` · ${rs.provider}` : " · demo data"}
                    </span>
                    <span className="text-[10px] font-mono text-gray-400">{formatDate(rs.observed_at)}</span>
                  </div>
                  <p className="text-sm font-medium text-gray-800 mt-1">{rs.headline}</p>
                  {rs.source_excerpt && <p className="text-xs text-gray-500 mt-1 leading-relaxed">{rs.source_excerpt}</p>}
                  {rs.source_url && (
                    <a
                      href={rs.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-rose-600 hover:underline mt-2"
                    >
                      Source <ExternalLink size={11} />
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <ConfirmModal
        open={modalOpen}
        title="Mark Under Active Evaluation"
        description={
          <>
            This is a <strong>one-way</strong> action. The signal will exit Horizon Radar and hand off
            to RPG's existing formal, restricted M&A process. It will drop off the live board and there
            is no way to undo this from here.
          </>
        }
        confirmLabel="Confirm hand-off"
        busy={submitting}
        onConfirm={handleConfirmEvaluation}
        onCancel={() => setModalOpen(false)}
      />
    </div>
  );
}

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
import { getEscalationBrief, getSignal, markUnderEvaluation } from "../services/api";
import ScoreBadge from "../components/ScoreBadge";
import ConfirmModal from "../components/ConfirmModal";
import EscalationBrief from "../components/EscalationBrief";
import type {
  EscalationBrief as EscalationBriefType,
  SignalClusterDetail,
} from "../types";

const SOURCE_ICONS: Record<string, LucideIcon> = {
  news: Newspaper,
  filings: FileText,
  patents: Gavel,
  hiring: Briefcase,
};

function iconFor(sourceType: string | undefined) {
  const key = (sourceType || "").toLowerCase();
  for (const prefix of Object.keys(SOURCE_ICONS)) {
    if (key.includes(prefix)) return SOURCE_ICONS[prefix];
  }
  return FileText;
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
        navigate("/", { replace: true });
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
    return <div className="text-sm text-ink-500 py-10 text-center">Loading signal…</div>;
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
        className="flex items-center gap-1.5 text-xs font-medium text-ink-500 hover:text-ink-200"
      >
        <ArrowLeft size={14} />
        Back
      </button>

      <div className="rounded-lg border border-ink-600 bg-ink-800 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-ink-100">{signal.entity_name}</h1>
            <p className="text-xs text-ink-500 mt-1">
              {(signal.entity_sectors || []).join(" · ")}
              {signal.entity_category ? ` — ${signal.entity_category}` : ""}
            </p>
            <div className="flex flex-wrap items-center gap-1.5 mt-3">
              {(signal.subsidiaries || []).map((code) => (
                <span
                  key={code}
                  className="rounded border border-ink-600 bg-ink-900 px-1.5 py-0.5 text-[10px] font-medium text-ink-400"
                >
                  Routed → {code}
                </span>
              ))}
            </div>
          </div>
          <ScoreBadge score={signal.score} size="lg" />
        </div>

        <div className="mt-4 rounded-md border border-ink-700 bg-ink-900 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-500 mb-1.5">
            Rationale
          </p>
          <p className="text-sm text-ink-200 leading-relaxed">{signal.rationale}</p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 mt-4">
          {(signal.signal_types || []).map((t) => (
            <span
              key={t}
              className="rounded border border-ink-600 bg-ink-900 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-500"
            >
              {t.replace(/_/g, " ")}
            </span>
          ))}
          <span
            className={`ml-auto rounded px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${
              signal.status === "under_evaluation"
                ? "bg-accent/15 text-accent-light"
                : "bg-ink-700 text-ink-400"
            }`}
          >
            {signal.status === "under_evaluation" ? "Under Active Evaluation" : "Live"}
          </span>
        </div>

        {signal.status === "under_evaluation" && (
          <div className="mt-4 flex items-start gap-2 rounded-md border border-accent/30 bg-accent/10 px-3 py-2.5">
            <ShieldCheck size={16} className="text-accent-light shrink-0 mt-0.5" />
            <p className="text-xs text-ink-300 leading-relaxed">
              This signal has exited the AI system. It was handed off to the formal M&A process
              {signal.evaluated_by ? ` by ${signal.evaluated_by}` : ""}
              {signal.evaluated_at ? ` on ${formatDate(signal.evaluated_at)}` : ""}. This action cannot
              be undone from here.
            </p>
          </div>
        )}

        {isAdmin && signal.status === "live" && (
          <div className="mt-5 flex justify-end">
            <button
              type="button"
              onClick={() => setModalOpen(true)}
              className="rounded-md bg-severity-high px-3.5 py-2 text-xs font-semibold text-white hover:bg-severity-high/90"
            >
              Mark Under Active Evaluation
            </button>
          </div>
        )}
      </div>

      {signal.status === "under_evaluation" && (
        <EscalationBrief brief={brief} entityName={signal.entity_name} />
      )}

      <div>
        <h2 className="text-sm font-semibold text-ink-200 mb-3">Contributing Raw Signals</h2>
        <ol className="space-y-3 border-l border-ink-700 pl-4">
          {rawSignals.map((rs, idx) => {
            const Icon = iconFor(rs.source_type);
            return (
              <li key={idx} className="relative">
                <span className="absolute -left-[22px] top-1 flex h-4 w-4 items-center justify-center rounded-full bg-ink-700 text-ink-300">
                  <Icon size={10} />
                </span>
                <div className="rounded-md border border-ink-600 bg-ink-800 p-3.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-500">
                      {rs.signal_type?.replace(/_/g, " ")} · {rs.source_type?.replace(/_/g, " ")}
                    </span>
                    <span className="text-[10px] font-mono text-ink-600">{formatDate(rs.observed_at)}</span>
                  </div>
                  <p className="text-sm font-medium text-ink-100 mt-1.5">{rs.headline}</p>
                  {rs.source_excerpt && (
                    <p className="text-xs text-ink-400 mt-1 leading-relaxed">{rs.source_excerpt}</p>
                  )}
                  {rs.source_url && (
                    <a
                      href={rs.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-accent-light hover:underline mt-2"
                    >
                      Source <ExternalLink size={11} />
                    </a>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
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

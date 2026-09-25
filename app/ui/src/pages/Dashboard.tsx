import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { Activity, AlertTriangle, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { usePageMeta } from "../context/PageMetaContext";
import { generateDigest, getSignals, getSubsidiaries, runIngest } from "../services/api";
import SubsidiaryFilterChip from "../components/SubsidiaryFilterChip";
import SignalCard from "../components/SignalCard";
import type { Subsidiary, SignalClusterSummary } from "../types";

const STATUS_OPTIONS = [
  { value: "live", label: "Live" },
  { value: "under_evaluation", label: "Under Evaluation" },
];

export default function Dashboard() {
  usePageMeta("Signal Board", "Flagged entities across subsidiaries within your reviewer scope.");

  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();

  const [subsidiaries, setSubsidiaries] = useState<Subsidiary[]>([]);
  const [signals, setSignals] = useState<SignalClusterSummary[]>([]);
  const [activeCode, setActiveCode] = useState<string | null>(null);
  const [status, setStatus] = useState("live");
  const [loading, setLoading] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [generating, setGenerating] = useState(false);

  const scopedCodes = useMemo(() => new Set(user?.subsidiary_scopes || []), [user]);

  const loadSubsidiaries = useCallback(async () => {
    try {
      const data = await getSubsidiaries();
      setSubsidiaries(data);
    } catch {
      // handled globally
    }
  }, []);

  const loadSignals = useCallback(async (subsidiary: string | null, statusFilter: string) => {
    setLoading(true);
    try {
      const params: { status: string; subsidiary?: string } = { status: statusFilter };
      if (subsidiary) params.subsidiary = subsidiary;
      const data = await getSignals(params);
      setSignals(data);
    } catch {
      setSignals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSubsidiaries();
  }, [loadSubsidiaries]);

  useEffect(() => {
    loadSignals(activeCode, status);
  }, [activeCode, status, loadSignals]);

  const handleChipClick = (subsidiary: Subsidiary) => {
    setActiveCode((prev) => (prev === subsidiary.code ? null : subsidiary.code));
  };

  const handleRunIngestion = async () => {
    setIngesting(true);
    try {
      const result = await runIngest();
      toast.success(
        `Ingestion complete — ${result.new_raw_signals} new raw signals, ${result.clusters_updated} clusters updated.`
      );
      await loadSignals(activeCode, status);
    } catch {
      // handled globally
    } finally {
      setIngesting(false);
    }
  };

  const handleGenerateDigest = async () => {
    setGenerating(true);
    try {
      const digest = await generateDigest();
      toast.success("Digest generated.");
      navigate(`/digests/${digest.id}`);
    } catch {
      // handled globally
    } finally {
      setGenerating(false);
    }
  };

  // Lightweight, client-side counts from the already-fetched signal list —
  // purely presentational, not a substitute for the real filtered fetch.
  const liveCount = signals.filter((s) => s.status === "live").length;
  const underEvalCount = signals.filter((s) => s.status === "under_evaluation").length;
  const highSeverityCount = signals.filter((s) => s.score >= 75).length;

  return (
    <div className="space-y-6">
      {isAdmin && (
        <div className="flex justify-end gap-2">
          <button type="button" onClick={handleRunIngestion} disabled={ingesting} className="btn btn-secondary btn-sm">
            <RefreshCw size={13} className={ingesting ? "animate-spin" : ""} />
            {ingesting ? "Running…" : "Run Ingestion"}
          </button>
          <button type="button" onClick={handleGenerateDigest} disabled={generating} className="btn btn-restricted btn-sm">
            <Sparkles size={13} />
            {generating ? "Generating…" : "Generate Digest"}
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
            <Activity size={18} className="text-blue-500" />
          </div>
          <div>
            <p className="text-xl font-bold text-gray-900">{liveCount}</p>
            <p className="text-xs text-gray-400">Live</p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center flex-shrink-0">
            <ShieldCheck size={18} className="text-amber-500" />
          </div>
          <div>
            <p className="text-xl font-bold text-gray-900">{underEvalCount}</p>
            <p className="text-xs text-gray-400">Under Evaluation</p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-rose-50 flex items-center justify-center flex-shrink-0">
            <AlertTriangle size={18} className="text-rose-500" />
          </div>
          <div>
            <p className="text-xl font-bold text-gray-900">{highSeverityCount}</p>
            <p className="text-xs text-gray-400">High Severity</p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {subsidiaries.map((s) => (
          <SubsidiaryFilterChip
            key={s.code}
            subsidiary={s}
            active={activeCode === s.code}
            disabled={!scopedCodes.has(s.code)}
            onClick={() => handleChipClick(s)}
          />
        ))}
      </div>

      <div className="flex items-center gap-1.5 border-b border-gray-100 pb-1">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setStatus(opt.value)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-t-lg transition-colors ${
              status === opt.value ? "text-rose-700 border-b-2 border-rose-600" : "text-gray-400 hover:text-gray-600"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-gray-400 py-10 justify-center">Loading signals…</div>
      ) : signals.length === 0 ? (
        <div className="text-sm text-gray-400 py-10 text-center border border-dashed border-gray-200 rounded-2xl">
          No signals match the current filters.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {signals.map((signal) => (
            <SignalCard key={signal.id} signal={signal} />
          ))}
        </div>
      )}
    </div>
  );
}

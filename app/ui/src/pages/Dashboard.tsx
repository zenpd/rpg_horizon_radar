import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { PlayCircle, RefreshCw, Sparkles } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { generateDigest, getSignals, getSubsidiaries, runIngest } from "../services/api";
import SubsidiaryFilterChip from "../components/SubsidiaryFilterChip";
import SignalCard from "../components/SignalCard";
import type { Subsidiary, SignalClusterSummary } from "../types";

const STATUS_OPTIONS = [
  { value: "live", label: "Live" },
  { value: "under_evaluation", label: "Under Evaluation" },
];

export default function Dashboard() {
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink-100">Signal Board</h1>
          <p className="text-sm text-ink-500 mt-0.5">
            Flagged entities across subsidiaries within your reviewer scope.
          </p>
        </div>

        {isAdmin && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRunIngestion}
              disabled={ingesting}
              className="flex items-center gap-1.5 rounded-md border border-ink-600 bg-ink-800 px-3 py-1.5 text-xs font-medium text-ink-200 hover:border-accent/50 disabled:opacity-50"
            >
              <RefreshCw size={14} className={ingesting ? "animate-spin" : ""} />
              {ingesting ? "Running…" : "Run Ingestion"}
            </button>
            <button
              type="button"
              onClick={handleGenerateDigest}
              disabled={generating}
              className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-dark disabled:opacity-50"
            >
              <Sparkles size={14} />
              {generating ? "Generating…" : "Generate Digest"}
            </button>
          </div>
        )}
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

      <div className="flex items-center gap-1.5 border-b border-ink-700 pb-1">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setStatus(opt.value)}
            className={`px-3 py-1.5 text-xs font-medium rounded-t-md ${
              status === opt.value
                ? "text-accent-light border-b-2 border-accent"
                : "text-ink-500 hover:text-ink-200"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-ink-500 py-10 justify-center">
          <PlayCircle size={16} className="animate-pulse" />
          Loading signals…
        </div>
      ) : signals.length === 0 ? (
        <div className="text-sm text-ink-500 py-10 text-center border border-dashed border-ink-700 rounded-lg">
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

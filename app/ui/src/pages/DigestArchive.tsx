import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CalendarDays } from "lucide-react";

import { getDigest, getDigests } from "../services/api";
import SignalCard from "../components/SignalCard";
import type { DigestDetail as DigestDetailType, DigestSummary, SignalClusterSummary } from "../types";

function formatDate(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return value;
  }
}

function DigestList() {
  const navigate = useNavigate();
  const [digests, setDigests] = useState<DigestSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDigests()
      .then(setDigests)
      .catch(() => setDigests([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-ink-100">Digest Archive</h1>
        <p className="text-sm text-ink-500 mt-0.5">Past weekly digest issues, in reviewer scope.</p>
      </div>

      {loading ? (
        <div className="text-sm text-ink-500 py-10 text-center">Loading digests…</div>
      ) : digests.length === 0 ? (
        <div className="text-sm text-ink-500 py-10 text-center border border-dashed border-ink-700 rounded-lg">
          No digests have been generated yet.
        </div>
      ) : (
        <div className="space-y-2.5">
          {digests.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => navigate(`/digests/${d.id}`)}
              className="w-full text-left rounded-lg border border-ink-600 bg-ink-800 p-4 hover:border-accent/50 hover:bg-ink-700/60 transition-colors"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <CalendarDays size={15} className="text-ink-500" />
                  <span className="text-sm font-medium text-ink-100">
                    {formatDate(d.period_start)} – {formatDate(d.period_end)}
                  </span>
                </div>
                <span className="text-[11px] font-mono text-ink-600">
                  Generated {formatDate(d.created_at)}
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-3">
                {Object.entries(d.subsidiary_breakdown || {}).map(([code, count]) => (
                  <span
                    key={code}
                    className="rounded border border-ink-600 bg-ink-900 px-2 py-0.5 text-[11px] font-medium text-ink-300"
                  >
                    {code}: {count}
                  </span>
                ))}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function DigestDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [digest, setDigest] = useState<DigestDetailType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getDigest(id)
      .then(setDigest)
      .catch(() => setDigest(null))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return <div className="text-sm text-ink-500 py-10 text-center">Loading digest…</div>;
  }

  if (!digest) {
    return <div className="text-sm text-ink-500 py-10 text-center">Digest not found.</div>;
  }

  // Each digest item is already scoped to a single subsidiary_code by the API
  // (one item per subsidiary a cluster was routed to), so grouping is a
  // straightforward bucket-by-code rather than fanning a multi-subsidiary
  // array out across groups.
  const groups: Record<string, SignalClusterSummary[]> = {};
  for (const item of digest.items || []) {
    const code = item.subsidiary_code || "Unassigned";
    if (!groups[code]) groups[code] = [];
    groups[code].push(item.cluster);
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <button
        type="button"
        onClick={() => navigate("/digests")}
        className="flex items-center gap-1.5 text-xs font-medium text-ink-500 hover:text-ink-200"
      >
        <ArrowLeft size={14} />
        Back to archive
      </button>

      <div>
        <h1 className="text-lg font-semibold text-ink-100">
          Digest — {formatDate(digest.period_start)} to {formatDate(digest.period_end)}
        </h1>
        <p className="text-xs text-ink-500 mt-1 font-mono">
          Generated {formatDate(digest.created_at)}
        </p>
      </div>

      {Object.keys(groups).length === 0 ? (
        <div className="text-sm text-ink-500 py-10 text-center border border-dashed border-ink-700 rounded-lg">
          This digest has no items.
        </div>
      ) : (
        Object.entries(groups).map(([code, items]) => (
          <div key={code}>
            <h2 className="text-sm font-semibold text-ink-200 mb-2.5 flex items-center gap-2">
              {code}
              <span className="text-[11px] font-normal text-ink-600">({items.length})</span>
            </h2>
            <div className="space-y-2">
              {items.map((item) => (
                <SignalCard key={item.id} signal={item} compact />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export default function DigestArchive() {
  return <DigestList />;
}

export { DigestDetail };

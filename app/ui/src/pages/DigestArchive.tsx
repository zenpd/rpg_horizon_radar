import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CalendarDays } from "lucide-react";

import { usePageMeta } from "../context/PageMetaContext";
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
  usePageMeta("Digest Archive", "Past weekly digest issues, in reviewer scope.");

  const navigate = useNavigate();
  const [digests, setDigests] = useState<DigestSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDigests()
      .then(setDigests)
      .catch(() => setDigests([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-sm text-gray-400 py-10 text-center">Loading digests…</div>;
  }

  if (digests.length === 0) {
    return (
      <div className="text-sm text-gray-400 py-10 text-center border border-dashed border-gray-200 rounded-2xl">
        No digests have been generated yet.
      </div>
    );
  }

  return (
    <div className="card overflow-hidden divide-y divide-gray-50">
      {digests.map((d) => (
        <button
          key={d.id}
          type="button"
          onClick={() => navigate(`/digests/${d.id}`)}
          className="w-full flex items-center gap-4 px-5 py-4 text-left hover:bg-gray-50/80 transition-colors"
        >
          <div className="w-9 h-9 rounded-xl bg-rose-50 flex items-center justify-center flex-shrink-0">
            <CalendarDays size={16} className="text-rose-500" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800">
              {formatDate(d.period_start)} – {formatDate(d.period_end)}
            </p>
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {Object.entries(d.subsidiary_breakdown || {}).map(([code, count]) => (
                <span key={code} className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-500">
                  {code}: {count}
                </span>
              ))}
            </div>
          </div>
          <span className="text-[11px] font-mono text-gray-400 flex-shrink-0">
            Generated {formatDate(d.created_at)}
          </span>
        </button>
      ))}
    </div>
  );
}

function DigestDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [digest, setDigest] = useState<DigestDetailType | null>(null);
  const [loading, setLoading] = useState(true);

  usePageMeta(
    digest ? `Digest — ${formatDate(digest.period_start)} to ${formatDate(digest.period_end)}` : "Digest",
    digest ? `Generated ${formatDate(digest.created_at)}` : undefined
  );

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getDigest(id)
      .then(setDigest)
      .catch(() => setDigest(null))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return <div className="text-sm text-gray-400 py-10 text-center">Loading digest…</div>;
  }

  if (!digest) {
    return <div className="text-sm text-gray-400 py-10 text-center">Digest not found.</div>;
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
        className="flex items-center gap-1.5 text-xs font-medium text-gray-400 hover:text-gray-700"
      >
        <ArrowLeft size={14} />
        Back to archive
      </button>

      {Object.keys(groups).length === 0 ? (
        <div className="text-sm text-gray-400 py-10 text-center border border-dashed border-gray-200 rounded-2xl">
          This digest has no items.
        </div>
      ) : (
        Object.entries(groups).map(([code, items]) => (
          <div key={code}>
            <h2 className="section-title flex items-center gap-2">
              {code}
              <span className="normal-case text-gray-300 font-normal">({items.length})</span>
            </h2>
            <div className="card overflow-hidden divide-y divide-gray-50">
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

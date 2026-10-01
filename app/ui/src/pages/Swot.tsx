import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import axios from "axios";
import { ChevronDown, ExternalLink, NotebookPen, RefreshCw } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { usePageMeta } from "../context/PageMetaContext";
import { getSubsidiaries, getSwot, getTeamNotes, putTeamNotes, rebuildSwot, waitForJob } from "../services/api";
import type { Subsidiary, SwotBrief, SwotEvidence, SwotItem, TeamNotes } from "../types";

const QUADRANTS = [
  { key: "strengths", label: "Strengths", tone: "border-emerald-200 bg-emerald-50/40", head: "text-emerald-700" },
  { key: "weaknesses", label: "Weaknesses", tone: "border-amber-200 bg-amber-50/40", head: "text-amber-700" },
  { key: "opportunities", label: "Opportunities", tone: "border-blue-200 bg-blue-50/40", head: "text-blue-700" },
  { key: "threats", label: "Threats", tone: "border-rose-200 bg-rose-50/40", head: "text-rose-700" },
] as const;

function formatDate(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return value;
  }
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return value;
  }
}

function SourceList({ ids, byId }: { ids: string[]; byId: Map<string, SwotEvidence> }) {
  return (
    <ul className="mt-2 space-y-1">
      {ids.map((id) => {
        const ev = byId.get(id);
        if (!ev) return null;
        const label =
          ev.kind === "team_note"
            ? "Strategy team note"
            : `${ev.entity} · ${ev.provider === "mock" ? "demo data" : ev.provider} · ${formatDate(ev.observed_at)}`;
        return (
          <li key={id} className="text-[11px] text-gray-500 leading-snug">
            <span className="font-semibold text-gray-600">{label}:</span> {ev.headline}
            {ev.url && (
              <a href={ev.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 ml-1 text-rose-600 hover:underline">
                source <ExternalLink size={10} />
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Item({ item, byId }: { item: SwotItem; byId: Map<string, SwotEvidence> }) {
  return (
    <li className="rounded-xl bg-white border border-gray-100 p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-gray-800">{item.text}</p>
        {item.impact != null && (
          <span className="shrink-0 text-[10px] font-mono text-gray-400" title="Impact / urgency, 0-100">
            {item.impact}/{item.urgency}
          </span>
        )}
      </div>
      {item.entity && <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mt-1">{item.entity}</p>}
      <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">
        <span className="font-semibold text-gray-600">Why: </span>
        {item.reasoning}
      </p>
      <SourceList ids={item.evidence} byId={byId} />
    </li>
  );
}

function TeamNotesEditor({ code, onSaved }: { code: string; onSaved: () => void }) {
  const [notes, setNotes] = useState<TeamNotes | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getTeamNotes(code).then(setNotes).catch(() => setNotes({ strengths: [], weaknesses: [] }));
  }, [code]);

  if (!notes) return null;
  const toText = (xs: string[]) => xs.join("\n");
  const fromText = (t: string) => t.split("\n");

  const save = async () => {
    setSaving(true);
    try {
      const saved = await putTeamNotes(code, { strengths: notes.strengths.filter((x) => x.trim()), weaknesses: notes.weaknesses.filter((x) => x.trim()) });
      setNotes(saved);
      toast.success("Team notes saved. Rebuild the brief to use them.");
      onSaved();
    } catch {
      // handled globally
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card p-5">
      <p className="section-title flex items-center gap-1.5">
        <NotebookPen size={12} /> Strategy team notes
      </p>
      <p className="text-xs text-gray-500 mb-3">
        Strengths and weaknesses describe the subsidiary itself, so the brief takes them only from these notes. One per line.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {(["strengths", "weaknesses"] as const).map((k) => (
          <label key={k} className="text-xs font-medium text-gray-500">
            {k === "strengths" ? "Strengths" : "Weaknesses"}
            <textarea
              rows={4}
              className="input mt-1.5 text-sm"
              value={toText(notes[k])}
              onChange={(e) => setNotes((n) => (n ? { ...n, [k]: fromText(e.target.value) } : n))}
            />
          </label>
        ))}
      </div>
      <button type="button" onClick={save} disabled={saving} className="btn btn-secondary btn-sm mt-3">
        {saving ? "Saving…" : "Save notes"}
      </button>
    </div>
  );
}

export default function Swot() {
  usePageMeta("SWOT Briefs", "What the watched companies' public signals mean for each subsidiary — every point cited.");
  const { user, isAdmin } = useAuth();

  const [subsidiaries, setSubsidiaries] = useState<Subsidiary[]>([]);
  const [code, setCode] = useState<string | null>(null);
  const [brief, setBrief] = useState<SwotBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [showHow, setShowHow] = useState(false);

  const visible = useMemo(
    () => subsidiaries.filter((s) => isAdmin || (s.compliance_gate && (user?.subsidiary_scopes || []).includes(s.code))),
    [subsidiaries, isAdmin, user]
  );

  useEffect(() => {
    getSubsidiaries().then(setSubsidiaries).catch(() => {});
  }, []);

  useEffect(() => {
    if (!code && visible.length) setCode((visible.find((s) => s.compliance_gate) || visible[0]).code);
  }, [visible, code]);

  const load = useCallback(async (c: string) => {
    setLoading(true);
    try {
      setBrief(await getSwot(c));
    } catch (err) {
      setBrief(null);
      if (!(axios.isAxiosError(err) && err.response?.status === 404)) toast.error("Could not load the SWOT brief.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (code) load(code);
  }, [code, load]);

  const rebuild = async () => {
    if (!code) return;
    setRebuilding(true);
    try {
      const job = await waitForJob(await rebuildSwot(code), 3000);
      if (job.status === "failed") toast.error(`The brief was not rebuilt: ${job.error}`);
      else toast.success("SWOT brief rebuilt.");
      await load(code);
    } catch {
      // handled globally
    } finally {
      setRebuilding(false);
    }
  };

  const byId = useMemo(() => new Map((brief?.evidence || []).map((e) => [e.id, e])), [brief]);
  const current = subsidiaries.find((s) => s.code === code);
  const signals = (brief?.evidence || []).filter((e) => e.kind === "signal");
  const realCount = signals.filter((e) => !e.fictional).length;
  const used = new Set(
    brief ? QUADRANTS.flatMap((q) => brief.content[q.key].flatMap((i) => i.evidence)) : []
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        {visible.map((s) => (
          <button
            key={s.code}
            type="button"
            onClick={() => setCode(s.code)}
            className={
              code === s.code
                ? "chip-open"
                : "rounded-full px-2.5 py-1 text-xs font-semibold bg-gray-50 text-gray-500 ring-1 ring-gray-200 hover:ring-rose-200"
            }
          >
            {s.name}
            {!s.compliance_gate && " (gate closed)"}
          </button>
        ))}
        {isAdmin && current?.compliance_gate && (
          <button type="button" onClick={rebuild} disabled={rebuilding} className="btn btn-restricted btn-sm ml-auto">
            <RefreshCw size={13} className={rebuilding ? "animate-spin" : ""} />
            {rebuilding ? "Building… (up to a few minutes)" : "Rebuild brief"}
          </button>
        )}
      </div>

      {visible.length === 0 ? (
        <div className="text-sm text-gray-400 py-10 text-center border border-dashed border-gray-200 rounded-2xl">
          No subsidiary in your scope has an open compliance gate.
        </div>
      ) : loading ? (
        <div className="text-sm text-gray-400 py-10 text-center">Loading brief…</div>
      ) : !brief ? (
        <div className="text-sm text-gray-400 py-10 text-center border border-dashed border-gray-200 rounded-2xl">
          {current?.compliance_gate
            ? "No SWOT brief yet. One is built after an ingestion run brings signals for this subsidiary" +
              (isAdmin ? ", or rebuild it now." : ".")
            : "This subsidiary's compliance gate is closed, so no signals are ingested for it."}
        </div>
      ) : (
        <>
          <div className="card p-5">
            <p className="section-title">Summary</p>
            <p className="text-sm text-gray-700 leading-relaxed">{brief.content.summary}</p>
            <p className="text-[11px] text-gray-400 mt-3">
              Built {formatDateTime(brief.generated_at)} by {brief.generated_by} from {signals.length} signals ({realCount} live,{" "}
              {signals.length - realCount} demo) and {brief.evidence.length - signals.length} team notes. Not a valuation or a deal
              recommendation.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {QUADRANTS.map((q) => {
              const items = brief.content[q.key];
              return (
                <div key={q.key} className={`rounded-2xl border p-4 ${q.tone}`}>
                  <p className={`text-xs font-bold uppercase tracking-widest mb-3 ${q.head}`}>{q.label}</p>
                  {items.length === 0 ? (
                    <p className="text-xs text-gray-400">
                      {q.key === "strengths" || q.key === "weaknesses"
                        ? "None — these come only from the strategy team's notes."
                        : "Nothing in the signals points here."}
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {items.map((item, i) => (
                        <Item key={i} item={item} byId={byId} />
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>

          <div className="card">
            <button type="button" onClick={() => setShowHow((v) => !v)} className="w-full flex items-center justify-between px-5 py-4 text-left">
              <span className="text-sm font-semibold text-gray-900">How this brief was built</span>
              <ChevronDown size={16} className={`text-gray-400 transition-transform ${showHow ? "rotate-180" : ""}`} />
            </button>
            {showHow && (
              <div className="px-5 pb-5 space-y-4 text-xs text-gray-600 leading-relaxed">
                <ol className="list-decimal pl-4 space-y-1">
                  <li>
                    Evidence: the {signals.length} most recent signals (last 120 days) of the companies routed to {current?.name}, plus the
                    strategy team's notes. Signals come from the live connectors for approved real companies and from demo data for the
                    fictional ones.
                  </li>
                  <li>
                    Draft: {brief.model} wrote the SWOT from that numbered evidence only, citing the items each point rests on and
                    explaining why.
                  </li>
                  <li>
                    Check: rules verified every citation exists, strengths and weaknesses rest only on team notes, opportunities and threats on
                    signals about the company they name, and scores are 0-100. Problems went back to the model for revision —{" "}
                    {brief.rounds === 1 ? "the first draft passed" : `it took ${brief.rounds} drafts`}.
                  </li>
                  <li>The brief never changes a signal score: scoring stays rule-based.</li>
                </ol>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-[10px] uppercase tracking-widest text-gray-400 font-bold border-b border-gray-100">
                        <th className="py-2 pr-3">Used</th>
                        <th className="py-2 pr-3">Company</th>
                        <th className="py-2 pr-3">Source</th>
                        <th className="py-2 pr-3">Date</th>
                        <th className="py-2">Evidence</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {brief.evidence.map((e) => (
                        <tr key={e.id}>
                          <td className="py-2 pr-3">{used.has(e.id) ? "✓" : ""}</td>
                          <td className="py-2 pr-3 whitespace-nowrap">{e.kind === "team_note" ? "Team note" : e.entity}</td>
                          <td className="py-2 pr-3 whitespace-nowrap">
                            {e.kind === "team_note" ? e.quadrant : e.provider === "mock" ? "demo data" : e.provider}
                          </td>
                          <td className="py-2 pr-3 whitespace-nowrap">{formatDate(e.observed_at)}</td>
                          <td className="py-2">
                            {e.headline}
                            {e.url && (
                              <a href={e.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 ml-1 text-rose-600 hover:underline">
                                <ExternalLink size={10} />
                              </a>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {isAdmin && code && current?.compliance_gate && <TeamNotesEditor code={code} onSaved={() => {}} />}
    </div>
  );
}

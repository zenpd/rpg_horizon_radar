import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import toast from "react-hot-toast";
import axios from "axios";
import { Building2, Plus, Radio, ScrollText, Trash2, Users } from "lucide-react";

import { usePageMeta } from "../context/PageMetaContext";
import {
  createReviewer,
  deleteReviewer,
  getAuditLog,
  getReviewers,
} from "../services/api";
import ConfirmModal from "../components/ConfirmModal";
import SourcesTab from "../components/admin/SourcesTab";
import WatchlistTab from "../components/admin/WatchlistTab";
import type { AuditLogEntry, Reviewer, ReviewerCreate } from "../types";

const TABS = [
  { key: "watchlist", label: "Watchlist", icon: Building2 },
  { key: "reviewers", label: "Users", icon: Users },
  { key: "sources", label: "Live Sources", icon: Radio },
  { key: "audit", label: "Activity", icon: ScrollText },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return value;
  }
}

// Maps raw activity action strings onto the four badge classes defined in index.css.
function actionBadgeClass(action: string): string {
  if (action === "mark_under_evaluation") return "action-escalate";
  if (["ingest_run", "watchlist_discovery", "swot_generated", "digest_generate", "radar_change"].includes(action)) return "action-write";
  if (["user_change", "watchlist_change"].includes(action)) return "action-admin";
  return "action-view";
}

function ReviewersTab() {
  const [reviewers, setReviewers] = useState<Reviewer[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<ReviewerCreate>({ name: "", email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Reviewer | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    setLoading(true);
    getReviewers()
      .then(setReviewers)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.password) return;
    setSubmitting(true);
    try {
      await createReviewer(form);
      toast.success("User added.");
      setForm({ name: "", email: "", password: "" });
      load();
    } catch (err) {
      if (!axios.isAxiosError(err) || !err.response) {
        toast.error("Could not add the user.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteReviewer(pendingDelete.id);
      toast.success(`Removed ${pendingDelete.name}.`);
      setReviewers((prev) => prev.filter((r) => r.id !== pendingDelete.id));
      setPendingDelete(null);
    } catch {
      // handled globally
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-widest text-gray-400 font-bold border-b border-gray-100">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Added</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-gray-400">
                  Loading users…
                </td>
              </tr>
            ) : reviewers.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-gray-400">
                  No users yet.
                </td>
              </tr>
            ) : (
              reviewers.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50/80 transition-colors">
                  <td className="px-4 py-3 text-gray-900 font-medium">{r.name}</td>
                  <td className="px-4 py-3 text-gray-500">{r.email}</td>
                  <td className="px-4 py-3 text-gray-400 font-mono text-xs">{formatDateTime(r.created_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => setPendingDelete(r)}
                      className="text-gray-400 hover:text-rose-600"
                      aria-label={`Remove ${r.name}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="card p-5">
        <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1.5">
          <Plus size={15} />
          Add user
        </h3>
        <p className="text-xs text-gray-400 mb-3">Every user sees every RPG company and can change the watchlist and the user list.</p>
        <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <input
            type="text"
            placeholder="Full name"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            required
            className="input"
          />
          <input
            type="email"
            placeholder="Email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            required
            className="input"
          />
          <input
            type="password"
            placeholder="Temporary password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            required
            className="input"
          />
          <div className="sm:col-span-2">
            <button type="submit" disabled={submitting} className="btn btn-restricted">
              {submitting ? "Adding…" : "Add user"}
            </button>
          </div>
        </form>
      </div>

      <ConfirmModal
        open={!!pendingDelete}
        title="Remove user"
        description={
          <>
            Remove <strong>{pendingDelete?.name}</strong>? They will no longer be able to sign in.
          </>
        }
        confirmLabel="Remove"
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}

function AuditTab() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    getAuditLog(100)
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);

  const actions = useMemo(() => ["all", ...Array.from(new Set(entries.map((e) => e.action)))], [entries]);

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      if (actionFilter !== "all" && e.action !== actionFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const haystack = `${e.reviewer_name_snapshot} ${e.resource_type} ${e.resource_id} ${e.detail || ""}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [entries, actionFilter, search]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} className="input w-auto">
          {actions.map((a) => (
            <option key={a} value={a}>
              {a === "all" ? "All actions" : a}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search user, resource, detail…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input flex-1 min-w-[200px]"
        />
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-widest text-gray-400 font-bold border-b border-gray-100">
              <th className="px-4 py-3">Timestamp</th>
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Resource</th>
              <th className="px-4 py-3">Detail</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-gray-400">
                  Loading activity…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-gray-400">
                  No matching entries.
                </td>
              </tr>
            ) : (
              filtered.map((e) => (
                <tr key={e.id} className="odd:bg-white even:bg-gray-50/50">
                  <td className="px-4 py-2.5 text-gray-500 font-mono whitespace-nowrap">{formatDateTime(e.created_at)}</td>
                  <td className="px-4 py-2.5 text-gray-700">{e.reviewer_name_snapshot}</td>
                  <td className="px-4 py-2.5">
                    <span className={actionBadgeClass(e.action)}>{e.action}</span>
                  </td>
                  <td className="px-4 py-2.5 text-gray-400 font-mono">
                    {e.resource_type}#{e.resource_id}
                  </td>
                  <td className="px-4 py-2.5 text-gray-500">{e.detail}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Admin() {
  usePageMeta("Users and watchlist", "Watched companies, users, live sources, and the activity history.");

  const [tab, setTab] = useState<TabKey>("watchlist");

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-semibold transition-all border ${
                active ? "bg-rose-600 text-white border-rose-600" : "bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100"
              }`}
            >
              <Icon size={13} />
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === "reviewers" && <ReviewersTab />}
      {tab === "watchlist" && <WatchlistTab />}
      {tab === "sources" && <SourcesTab />}
      {tab === "audit" && <AuditTab />}
    </div>
  );
}

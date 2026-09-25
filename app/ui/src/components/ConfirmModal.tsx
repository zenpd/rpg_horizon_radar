import type { ReactNode } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmModalProps {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmModal({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = true,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-md rounded-lg border border-ink-600 bg-ink-800 shadow-xl">
        <div className="flex items-start justify-between border-b border-ink-600 px-5 py-4">
          <div className="flex items-center gap-2">
            {danger && <AlertTriangle size={18} className="text-severity-high" />}
            <h2 className="text-sm font-semibold text-ink-100">{title}</h2>
          </div>
          <button onClick={onCancel} className="text-ink-500 hover:text-ink-100" aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="px-5 py-4 text-sm text-ink-300 leading-relaxed">{description}</div>
        <div className="flex justify-end gap-2 border-t border-ink-600 px-5 py-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-ink-600 px-3 py-1.5 text-xs font-medium text-ink-300 hover:bg-ink-700 disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50 ${
              danger ? "bg-severity-high hover:bg-severity-high/90" : "bg-accent hover:bg-accent-dark"
            }`}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

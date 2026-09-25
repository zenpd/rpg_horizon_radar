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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/40 backdrop-blur-sm px-4">
      <div className="w-full max-w-md card animate-slide-up overflow-hidden">
        <div className="flex items-start justify-between border-b border-gray-100 px-5 py-4">
          <div className="flex items-center gap-2">
            {danger && <AlertTriangle size={18} className="text-rose-500" />}
            <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
          </div>
          <button onClick={onCancel} className="text-gray-400 hover:text-gray-700" aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="px-5 py-4 text-sm text-gray-600 leading-relaxed">{description}</div>
        <div className="flex justify-end gap-2 border-t border-gray-100 bg-gray-50/50 px-5 py-3">
          <button type="button" onClick={onCancel} disabled={busy} className="btn btn-secondary btn-sm">
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={danger ? "btn btn-danger btn-sm" : "btn btn-restricted btn-sm"}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

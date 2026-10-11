import type { ReactNode } from "react";
import { X } from "lucide-react";

interface DetailDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** One line stating exactly how the figure was derived — the "justify the number" line. */
  basis?: string;
  children: ReactNode;
}

/** A right-hand slide-over for "why is this number what it is" drill-downs — every clickable
 * KPI/chart/card on the Executive Dashboard opens one of these onto the real underlying
 * records, rather than a fabricated summary. */
export default function DetailDrawer({ open, onClose, title, basis, children }: DetailDrawerProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white h-full shadow-2xl flex flex-col animate-[slideIn_.18s_ease-out]">
        <div className="flex items-start justify-between gap-3 border-b border-gray-100 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
            {basis && <p className="text-[11px] text-gray-400 mt-0.5 leading-relaxed">{basis}</p>}
          </div>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600 flex-shrink-0 mt-0.5" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

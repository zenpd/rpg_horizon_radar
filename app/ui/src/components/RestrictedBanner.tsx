import { ShieldAlert } from "lucide-react";

export default function RestrictedBanner() {
  return (
    <div className="bg-severity-high/10 border-b border-severity-high/40 px-4 py-2 sm:px-6">
      <div className="flex items-start gap-2.5 max-w-screen-2xl mx-auto">
        <ShieldAlert size={18} className="text-severity-high shrink-0 mt-0.5" />
        <div className="leading-tight">
          <p className="text-severity-high font-semibold text-xs tracking-wide uppercase">
            Restricted — UPSI-Adjacent — Do Not Forward
          </p>
          <p className="text-ink-500 text-[11px] mt-0.5">
            This is a signal-flagging tool, not a valuation or due-diligence tool.
          </p>
        </div>
      </div>
    </div>
  );
}

import { Radar } from "lucide-react";

export default function Footer() {
  return (
    <footer className="fixed bottom-0 left-[240px] right-0 h-[44px] bg-white border-t border-gray-100 flex items-center justify-between px-6 z-20">
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <Radar size={12} className="text-rose-500" />
        <span className="font-semibold text-gray-500">RPG Horizon Radar</span>
        <span>·</span>
        <span>ZenLabs Agent Foundry</span>
        <span>·</span>
        <span>Corporate Strategy (Restricted)</span>
      </div>

      <div className="flex items-center gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse-dot" />
          Every view is audit-logged
        </span>
      </div>
    </footer>
  );
}

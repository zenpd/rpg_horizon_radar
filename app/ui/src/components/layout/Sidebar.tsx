import { NavLink } from "react-router-dom";
import { LayoutDashboard, Newspaper, Radar, ShieldCheck } from "lucide-react";
import clsx from "clsx";

import { useAuth } from "../../context/AuthContext";

const NAV = [
  { label: "Signal Board", icon: LayoutDashboard, path: "/" },
  { label: "Digest Archive", icon: Newspaper, path: "/digests" },
];

export default function Sidebar() {
  const { isAdmin } = useAuth();

  return (
    <aside className="fixed top-0 left-0 bottom-0 w-[240px] bg-white shadow-sidebar z-30 flex flex-col">
      {/* Logo */}
      <div className="h-[60px] flex items-center px-5 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="relative w-8 h-8 rounded-xl bg-gradient-restricted flex items-center justify-center shadow-glow-restricted flex-shrink-0">
            <Radar size={16} className="text-white" />
          </div>
          <div>
            <span className="font-extrabold text-gray-900 text-base tracking-tight">RPG</span>
            <span className="block text-[10px] font-medium text-gray-400 -mt-0.5 tracking-wide uppercase">
              Horizon Radar
            </span>
          </div>
        </div>
      </div>

      {/* Main nav */}
      <div className="flex-1 overflow-y-auto px-3 py-4">
        <p className="section-title px-1 mb-2">Corporate Strategy</p>
        <nav className="space-y-0.5">
          {NAV.map(({ label, icon: Icon, path }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={({ isActive }) => clsx("sidebar-link", isActive && "active")}
            >
              <Icon size={16} />
              <span className="flex-1">{label}</span>
            </NavLink>
          ))}

          {isAdmin && (
            <NavLink to="/admin" className={({ isActive }) => clsx("sidebar-link", isActive && "active")}>
              <ShieldCheck size={16} />
              <span className="flex-1">Admin</span>
            </NavLink>
          )}
        </nav>
      </div>

      {/* Restricted-access reminder pill */}
      <div className="px-4 py-2.5 border-t border-gray-100">
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-rose-50 border border-rose-100">
          <span className="live-dot flex-shrink-0 [&::before]:bg-rose-300 [&::after]:bg-rose-500" />
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-bold text-rose-700 uppercase tracking-wide">Access restricted</p>
            <p className="text-[10px] text-rose-600/70">Named reviewers only</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

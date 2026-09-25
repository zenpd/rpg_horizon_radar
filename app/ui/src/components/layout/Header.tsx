import { LogOut } from "lucide-react";

import { useAuth } from "../../context/AuthContext";
import { usePageMetaContext } from "../../context/PageMetaContext";

export default function Header() {
  const { user, logout } = useAuth();
  const { meta } = usePageMetaContext();

  return (
    <header className="fixed top-0 left-[240px] right-0 h-[60px] bg-white shadow-header z-20 flex items-center justify-between px-6 gap-4">
      {/* Page title */}
      <div className="min-w-0">
        <h1 className="text-sm font-semibold text-gray-900 truncate">{meta.title}</h1>
        {meta.subtitle && <p className="text-xs text-gray-400 truncate">{meta.subtitle}</p>}
      </div>

      {/* Reviewer identity + logout */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <div className="hidden lg:flex items-center gap-1">
          {(user?.subsidiary_scopes || []).map((code) => (
            <span key={code} className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-500">
              {code}
            </span>
          ))}
        </div>

        <div className="flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-xl border border-gray-100">
          <div className="w-7 h-7 rounded-full bg-gradient-restricted flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {(user?.name || "?").slice(0, 1)}
          </div>
          <div className="hidden sm:flex flex-col items-start leading-none">
            <span className="text-xs font-semibold text-gray-700">{user?.name}</span>
            <span className="text-[10px] text-gray-400 mt-0.5">
              {user?.role === "compliance_admin" ? "Compliance Admin" : "Corp Strategy Reviewer"}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={logout}
          className="flex items-center gap-1.5 rounded-xl border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-500 hover:border-rose-300 hover:text-rose-600 hover:bg-rose-50 transition-colors"
        >
          <LogOut size={14} />
          Logout
        </button>
      </div>
    </header>
  );
}

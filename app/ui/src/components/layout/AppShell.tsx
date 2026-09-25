import { NavLink, Outlet } from "react-router-dom";
import { LogOut, Radar, ShieldCheck } from "lucide-react";

import { useAuth } from "../../context/AuthContext";
import RestrictedBanner from "../RestrictedBanner";

export default function AppShell() {
  const { user, isAdmin, logout } = useAuth();

  return (
    <div className="min-h-screen bg-ink-950 text-ink-100 flex flex-col">
      <header className="border-b border-ink-700 bg-ink-900">
        <div className="max-w-screen-2xl mx-auto flex items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <Radar size={20} className="text-accent" />
            <div className="leading-tight">
              <p className="text-sm font-semibold tracking-wide">RPG Horizon Radar</p>
              <p className="text-[10px] text-ink-500 uppercase tracking-wider">Corporate Strategy</p>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-1 text-sm">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md font-medium ${
                  isActive ? "bg-ink-700 text-ink-100" : "text-ink-400 hover:text-ink-100"
                }`
              }
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/digests"
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md font-medium ${
                  isActive ? "bg-ink-700 text-ink-100" : "text-ink-400 hover:text-ink-100"
                }`
              }
            >
              Digest Archive
            </NavLink>
            {isAdmin && (
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  `flex items-center gap-1 px-3 py-1.5 rounded-md font-medium ${
                    isActive ? "bg-ink-700 text-ink-100" : "text-ink-400 hover:text-ink-100"
                  }`
                }
              >
                <ShieldCheck size={14} />
                Admin
              </NavLink>
            )}
          </nav>

          <div className="flex items-center gap-3">
            <div className="hidden sm:flex flex-col items-end leading-tight">
              <span className="text-sm font-medium text-ink-100">{user?.name}</span>
              <span className="text-[10px] uppercase tracking-wide text-ink-500">
                {user?.role === "compliance_admin" ? "Compliance Admin" : "Corp Strategy Reviewer"}
              </span>
            </div>
            <div className="hidden lg:flex items-center gap-1">
              {(user?.subsidiary_scopes || []).map((code) => (
                <span
                  key={code}
                  className="rounded border border-ink-600 bg-ink-800 px-1.5 py-0.5 text-[10px] font-medium text-ink-400"
                >
                  {code}
                </span>
              ))}
            </div>
            <button
              type="button"
              onClick={logout}
              className="flex items-center gap-1.5 rounded-md border border-ink-600 px-2.5 py-1.5 text-xs font-medium text-ink-400 hover:border-severity-high/50 hover:text-severity-high"
            >
              <LogOut size={14} />
              Logout
            </button>
          </div>
        </div>

        {/* Mobile nav */}
        <div className="flex md:hidden items-center gap-1 px-4 pb-2 text-xs">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `px-2.5 py-1 rounded font-medium ${isActive ? "bg-ink-700 text-ink-100" : "text-ink-400"}`
            }
          >
            Dashboard
          </NavLink>
          <NavLink
            to="/digests"
            className={({ isActive }) =>
              `px-2.5 py-1 rounded font-medium ${isActive ? "bg-ink-700 text-ink-100" : "text-ink-400"}`
            }
          >
            Digests
          </NavLink>
          {isAdmin && (
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                `px-2.5 py-1 rounded font-medium ${isActive ? "bg-ink-700 text-ink-100" : "text-ink-400"}`
              }
            >
              Admin
            </NavLink>
          )}
        </div>
      </header>

      <RestrictedBanner />

      <main className="flex-1 max-w-screen-2xl w-full mx-auto px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}

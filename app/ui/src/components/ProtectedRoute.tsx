import { useEffect } from "react";
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import toast from "react-hot-toast";

import { useAuth } from "../context/AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50 text-slate-500 text-sm gap-2">
        <div className="w-4 h-4 border-2 border-zen-200 border-t-zen-500 rounded-full animate-spin" />
        Loading session…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export function AdminRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isAdmin, loading } = useAuth();

  useEffect(() => {
    if (!loading && isAuthenticated && !isAdmin) {
      toast.error("You don't have access to this action");
    }
  }, [loading, isAuthenticated, isAdmin]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50 text-slate-500 text-sm gap-2">
        <div className="w-4 h-4 border-2 border-zen-200 border-t-zen-500 rounded-full animate-spin" />
        Loading session…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

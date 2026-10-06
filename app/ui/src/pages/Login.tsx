import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { Radar } from "lucide-react";
import axios from "axios";

import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  // Pre-filled for local demo convenience only — still editable, so a
  // presenter can switch to a scoped reviewer login when that's the point.
  const [email, setEmail] = useState("compliance.admin@rpg-demo.local");
  const [password, setPassword] = useState("ChangeMe123!");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/overview", { replace: true });
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.status === 401
          ? "Invalid email or password."
          : "Login failed. Please try again.";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-gradient-restricted flex items-center justify-center shadow-glow-restricted mb-3">
            <Radar size={26} className="text-white" />
          </div>
          <h1 className="text-lg font-extrabold text-gray-900 tracking-tight">RPG Horizon Radar</h1>
          <p className="text-xs text-gray-400 mt-2 max-w-xs leading-relaxed">
            Restricted — Corporate Strategy. Named-reviewer access only. Contact Compliance to be
            added to the reviewer list.
          </p>
        </div>

        <div className="card p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="input"
                placeholder="you@rpgroup.com"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="input"
                placeholder="••••••••"
              />
            </div>
            <button type="submit" disabled={submitting} className="btn btn-restricted w-full justify-center">
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="text-center text-[11px] text-gray-400 mt-4">
          This is a signal-flagging tool, not a valuation or due-diligence tool.
        </p>
      </div>
    </div>
  );
}

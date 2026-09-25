import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { Radar, ShieldAlert } from "lucide-react";
import axios from "axios";

import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
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
    <div className="min-h-screen bg-ink-950 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-6">
          <Radar size={22} className="text-accent" />
          <span className="text-ink-100 font-semibold tracking-wide">RPG Horizon Radar</span>
        </div>

        <div className="rounded-lg border border-ink-600 bg-ink-800 p-6 shadow-xl">
          <div className="flex items-start gap-2 rounded-md border border-severity-high/30 bg-severity-high/10 px-3 py-2.5 mb-5">
            <ShieldAlert size={16} className="text-severity-high shrink-0 mt-0.5" />
            <p className="text-xs text-ink-300 leading-relaxed">
              Named-reviewer access only. Contact Compliance to be added to the reviewer list.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-ink-400 mb-1.5" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full rounded-md border border-ink-600 bg-ink-900 px-3 py-2 text-sm text-ink-100 placeholder:text-ink-600 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="you@rpgroup.com"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-ink-400 mb-1.5" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full rounded-md border border-ink-600 bg-ink-900 px-3 py-2 text-sm text-ink-100 placeholder:text-ink-600 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="••••••••"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-accent hover:bg-accent-dark text-white text-sm font-semibold py-2 transition-colors disabled:opacity-50"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <p className="text-center text-[11px] text-ink-600 mt-4">
          This is a signal-flagging tool, not a valuation or due-diligence tool.
        </p>
      </div>
    </div>
  );
}

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
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/dashboard", { replace: true });
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
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-lg shadow-lg border border-gray-200 p-8 w-full max-w-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-lg bg-gradient-zen flex items-center justify-center text-white flex-shrink-0">
            <Radar size={22} />
          </div>
          <div>
            <div className="font-bold text-slate-900">Horizon Radar</div>
            <div className="text-xs text-slate-600">RPG Corporate Strategy</div>
          </div>
        </div>

        <h2 className="text-lg font-semibold text-slate-900">Sign in to continue</h2>
        <p className="text-xs text-slate-600 mt-1 mb-4 leading-relaxed">
          Restricted — Corporate Strategy. Named-reviewer access only. Contact Compliance to be
          added to the reviewer list.
        </p>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="text-xs text-slate-600" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zen-400"
              placeholder="you@rpgroup.com"
            />
          </div>
          <div>
            <label className="text-xs text-slate-600" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zen-400"
              placeholder="••••••••"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-gradient-zen text-white py-2 rounded-lg text-sm font-medium disabled:opacity-50 hover:opacity-90"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-xs text-slate-500 mt-4">
          This is a signal-flagging tool, not a valuation or due-diligence tool.
        </p>
      </div>
    </div>
  );
}

"use client";

import { useState, FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, register } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/tws";

  const [tab, setTab]         = useState<"login" | "register">("login");
  const [email, setEmail]     = useState("");
  const [password, setPassword] = useState("");
  const [name, setName]       = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (tab === "login") {
        await login(email, password);
      } else {
        await register(email, password, name || undefined);
      }
      router.push(next);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#08080f] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="text-3xl font-bold text-white tracking-tight">LokiStock</div>
          <div className="text-sm text-[#6666aa] mt-1">Your personal trading intelligence</div>
        </div>

        {/* Card */}
        <div className="bg-[#0f0f1a] border border-[#2e2e50] rounded-2xl overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-[#2e2e50]">
            {(["login", "register"] as const).map((t) => (
              <button
                key={t}
                onClick={() => { setTab(t); setError(null); }}
                className={`flex-1 py-3.5 text-sm font-medium transition-colors ${
                  tab === t
                    ? "text-white border-b-2 border-[#7c5cfc]"
                    : "text-[#6666aa] hover:text-white"
                }`}
              >
                {t === "login" ? "Sign In" : "Create Account"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            {tab === "register" && (
              <div>
                <label className="block text-xs text-[#6666aa] mb-1.5">Display name (optional)</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  className="w-full bg-[#16162a] border border-[#2e2e50] rounded-lg px-3.5 py-2.5 text-sm text-white placeholder-[#44445a] focus:outline-none focus:border-[#7c5cfc] transition-colors"
                />
              </div>
            )}

            <div>
              <label className="block text-xs text-[#6666aa] mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="w-full bg-[#16162a] border border-[#2e2e50] rounded-lg px-3.5 py-2.5 text-sm text-white placeholder-[#44445a] focus:outline-none focus:border-[#7c5cfc] transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs text-[#6666aa] mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                minLength={6}
                className="w-full bg-[#16162a] border border-[#2e2e50] rounded-lg px-3.5 py-2.5 text-sm text-white placeholder-[#44445a] focus:outline-none focus:border-[#7c5cfc] transition-colors"
              />
            </div>

            {error && (
              <div className="text-xs text-[#ff5252] bg-[#ff52521a] border border-[#ff525240] rounded-lg px-3 py-2.5">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg font-semibold text-sm bg-[#7c5cfc] hover:bg-[#8f72ff] disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors"
            >
              {loading ? "Please wait…" : tab === "login" ? "Sign In" : "Create Account"}
            </button>

            {tab === "login" && (
              <p className="text-center text-xs text-[#44445a]">
                Forgot password?{" "}
                <span className="text-[#7c5cfc]">Contact support</span>
              </p>
            )}
          </form>
        </div>

        <p className="text-center text-xs text-[#44445a] mt-6">
          Analytics are free — login is only needed to connect your broker account.
        </p>
      </div>
    </div>
  );
}

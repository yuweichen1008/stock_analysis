"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { saveBrokerCreds, deleteBrokerCreds, getBrokerCredsStatus } from "@/lib/api";

// ── Small sub-components ───────────────────────────────────────────────────────

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-[#0f0f1a] border border-[#2e2e50] rounded-2xl p-5">
      <h2 className="text-sm font-semibold text-[#6666aa] uppercase tracking-wider mb-4">{title}</h2>
      {children}
    </div>
  );
}

function StatusBadge({ configured }: { configured: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium ${
      configured
        ? "bg-[#00e67620] text-[#00e676] border border-[#00e67640]"
        : "bg-[#ffffff10] text-[#6666aa] border border-[#2e2e50]"
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${configured ? "bg-[#00e676]" : "bg-[#6666aa]"}`} />
      {configured ? "Connected" : "Not connected"}
    </span>
  );
}

// ── Broker card ───────────────────────────────────────────────────────────────

interface BrokerCardProps {
  broker:       "ctbc" | "moomoo";
  title:        string;
  description:  string;
  fields:       { key: string; label: string; placeholder: string; type?: string }[];
  onSaved:      () => void;
}

function BrokerCard({ broker, title, description, fields, onSaved }: BrokerCardProps) {
  const [configured, setConfigured] = useState(false);
  const [showForm, setShowForm]     = useState(false);
  const [values, setValues]         = useState<Record<string, string>>({});
  const [saving, setSaving]         = useState(false);
  const [error, setError]           = useState<string | null>(null);

  useEffect(() => {
    getBrokerCredsStatus(broker)
      .then((s) => setConfigured(s.configured))
      .catch(() => {});
  }, [broker]);

  const handleSave = async () => {
    setError(null);
    setSaving(true);
    try {
      await saveBrokerCreds(broker, values);
      setConfigured(true);
      setShowForm(false);
      setValues({});
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save credentials");
    } finally {
      setSaving(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await deleteBrokerCreds(broker);
      setConfigured(false);
      setShowForm(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to disconnect");
    }
  };

  return (
    <div className="bg-[#16162a] border border-[#2e2e50] rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <div className="text-sm font-semibold text-white">{title}</div>
          <div className="text-xs text-[#6666aa] mt-0.5">{description}</div>
        </div>
        <StatusBadge configured={configured} />
      </div>

      {error && (
        <div className="text-xs text-[#ff5252] bg-[#ff52521a] border border-[#ff525240] rounded-lg px-3 py-2 mb-3">
          {error}
        </div>
      )}

      {showForm ? (
        <div className="mt-3 space-y-3">
          {fields.map((f) => (
            <div key={f.key}>
              <label className="block text-xs text-[#6666aa] mb-1">{f.label}</label>
              <input
                type={f.type ?? "text"}
                value={values[f.key] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                placeholder={f.placeholder}
                className="w-full bg-[#0f0f1a] border border-[#2e2e50] rounded-lg px-3 py-2 text-sm text-white placeholder-[#44445a] focus:outline-none focus:border-[#7c5cfc] transition-colors"
              />
            </div>
          ))}
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex-1 py-2 rounded-lg text-sm font-medium bg-[#7c5cfc] hover:bg-[#8f72ff] disabled:opacity-50 text-white transition-colors"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              onClick={() => { setShowForm(false); setValues({}); setError(null); }}
              className="px-4 py-2 rounded-lg text-sm font-medium text-[#6666aa] hover:text-white border border-[#2e2e50] transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => setShowForm(true)}
            className="flex-1 py-2 rounded-lg text-sm font-medium bg-[#2e2e50] hover:bg-[#3a3a65] text-white transition-colors"
          >
            {configured ? "Update credentials" : "Connect"}
          </button>
          {configured && (
            <button
              onClick={handleDisconnect}
              className="px-3 py-2 rounded-lg text-sm font-medium text-[#ff5252] hover:bg-[#ff52521a] border border-[#ff525240] transition-colors"
            >
              Disconnect
            </button>
          )}
        </div>
      )}
    </div>
  );
}


// ── Main page ─────────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const { user, logout, refreshUser, isLoggedIn } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoggedIn === false && user === null) {
      // Only redirect after the initial mount has resolved (avoids flash)
      const t = setTimeout(() => {
        if (!isLoggedIn) router.push("/login?next=/profile");
      }, 200);
      return () => clearTimeout(t);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoggedIn]);

  if (!user) {
    return (
      <div className="flex-1 flex items-center justify-center text-[#6666aa]">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 max-w-lg mx-auto w-full space-y-5">
      {/* User card */}
      <SectionCard title="Account">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-full bg-[#7c5cfc33] flex items-center justify-center text-xl font-bold text-[#7c5cfc]">
            {(user.display_name || user.email || "?")[0].toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-white truncate">{user.display_name}</div>
            <div className="text-xs text-[#6666aa] truncate">{user.email ?? "No email"}</div>
          </div>
          <div className="text-right">
            <div className="text-xs text-[#6666aa]">Coins</div>
            <div className="text-sm font-semibold text-[#ffd700]">{user.coins.toLocaleString()}</div>
          </div>
        </div>
        <button
          onClick={() => { logout(); router.push("/"); }}
          className="mt-4 w-full py-2 rounded-lg text-sm font-medium text-[#ff5252] hover:bg-[#ff52521a] border border-[#ff525240] transition-colors"
        >
          Sign out
        </button>
      </SectionCard>

      {/* Broker credentials */}
      <SectionCard title="Broker Accounts">
        <div className="space-y-3">
          <BrokerCard
            broker="ctbc"
            title="CTBC 中信亮點"
            description="Taiwan stocks — Win168 account credentials"
            fields={[
              { key: "id",       label: "Win168 ID (身分證/帳號)", placeholder: "A123456789" },
              { key: "password", label: "Password (密碼)",         placeholder: "••••••••",  type: "password" },
            ]}
            onSaved={refreshUser}
          />
          <BrokerCard
            broker="moomoo"
            title="Moomoo / Futu"
            description="US stocks — OpenD host and port"
            fields={[
              { key: "host", label: "OpenD Host", placeholder: "127.0.0.1" },
              { key: "port", label: "OpenD Port", placeholder: "11111" },
            ]}
            onSaved={refreshUser}
          />
        </div>
        <p className="text-xs text-[#44445a] mt-4">
          Credentials are encrypted server-side using AES-256. They are never stored in plain text
          and are never exposed back through the API.
        </p>
      </SectionCard>

      {/* Security note */}
      <SectionCard title="Security">
        <div className="space-y-2 text-sm text-[#6666aa]">
          <div className="flex items-start gap-2">
            <span className="text-[#7c5cfc] mt-0.5">&#x2022;</span>
            <span>All connections use HTTPS / TLS in transit</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#7c5cfc] mt-0.5">&#x2022;</span>
            <span>Broker credentials encrypted with Fernet AES-128 at rest</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#7c5cfc] mt-0.5">&#x2022;</span>
            <span>Your decrypted credentials are used only at request time and are never logged</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#7c5cfc] mt-0.5">&#x2022;</span>
            <span>Session token expires after 7 days — re-login required</span>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}

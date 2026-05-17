"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import type { AccountSnapshot, BrokerBalance } from "@/lib/types";
import { brokerBalance, brokerAssetHistory } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { LogType } from "@/components/TerminalLog";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PortfolioHeroProps {
  market: "TW" | "US";
  onLog?: (type: LogType, msg: string) => void;
}

type Period = "1W" | "1M" | "3M" | "YTD" | "1Y";

// ── Helpers ───────────────────────────────────────────────────────────────────

function ytdDays(): number {
  const now = new Date();
  const startOfYear = new Date(now.getFullYear(), 0, 1);
  return Math.ceil((now.getTime() - startOfYear.getTime()) / (1000 * 60 * 60 * 24));
}

const PERIOD_DAYS: Record<Period, number> = {
  "1W":  7,
  "1M":  30,
  "3M":  90,
  "YTD": ytdDays(),
  "1Y":  365,
};

const PERIODS: Period[] = ["1W", "1M", "3M", "YTD", "1Y"];

function shortDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch {
    return dateStr;
  }
}

function formatNT(value: number, decimals = 0): string {
  return `NT$${value.toLocaleString("zh-TW", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

function formatUSD(value: number): string {
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatValue(value: number, market: "TW" | "US"): string {
  return market === "TW" ? formatNT(value) : formatUSD(value);
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className="px-6 pt-6 pb-4 bg-[#0f0f1a] animate-pulse space-y-3">
      <div className="h-10 w-48 bg-[#2e2e50] rounded" />
      <div className="h-5 w-32 bg-[#2e2e50] rounded" />
      <div className="h-32 w-full bg-[#2e2e50] rounded" />
    </div>
  );
}

// ── Not-logged-in placeholder ─────────────────────────────────────────────────

function NotLoggedIn() {
  return (
    <div className="px-6 pt-6 pb-4 bg-[#0f0f1a] border-b border-[#2e2e50]">
      <p className="text-xs text-[#555570] uppercase tracking-wide mb-1">Total Portfolio Value</p>
      <p className="text-4xl font-bold text-white mb-1">—</p>
      <p className="text-sm text-[#8888aa]">Login to see your balance</p>
    </div>
  );
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

interface TooltipPayloadItem {
  value: number;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
  market: "TW" | "US";
}

function CustomTooltip({ active, payload, label, market }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const val = payload[0].value;
  return (
    <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-lg px-3 py-2">
      <p className="text-[10px] text-[#8888aa] mb-0.5">{label}</p>
      <p className="text-sm font-bold text-white">{formatValue(val, market)}</p>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PortfolioHero({ market, onLog }: PortfolioHeroProps) {
  const [balance,    setBalance]    = useState<BrokerBalance | null>(null);
  const [history,   setHistory]    = useState<AccountSnapshot[]>([]);
  const [loading,   setLoading]    = useState(true);
  const [activePeriod, setActivePeriod] = useState<Period>("1M");
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    setIsLoggedIn(!!getToken());
  }, []);

  useEffect(() => {
    if (!isLoggedIn) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);

    const log = (type: LogType, msg: string) => onLog?.(type, msg);

    const marketLabel = market === "TW" ? "TW" : "US";

    Promise.all([
      (async () => {
        log("fetch", `GET /api/broker/balance?market=${marketLabel}`);
        const b = await brokerBalance(market);
        if (!cancelled) {
          setBalance(b);
          log("success", `Balance loaded: ${formatValue(b.total_value, market)}`);
        }
      })(),
      (async () => {
        log("fetch", `GET /api/broker/asset-history?market=${marketLabel}&days=365`);
        const h = await brokerAssetHistory(market, 365);
        if (!cancelled) {
          setHistory(h);
          log("info", `Asset history: ${h.length} snapshots`);
        }
      })(),
    ])
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "Unknown error";
        log("error", `PortfolioHero fetch failed: ${msg}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [isLoggedIn, market, onLog]);

  // Filter history by selected period
  const filteredHistory = useMemo(() => {
    if (!history.length) return [];
    const days = PERIOD_DAYS[activePeriod];
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    return history
      .filter(s => s.total_value != null && new Date(s.date) >= cutoff)
      .map(s => ({ date: shortDate(s.date), rawDate: s.date, value: s.total_value as number }));
  }, [history, activePeriod]);

  // Today's P&L: last snapshot minus second-to-last
  const todayPnl = useMemo(() => {
    const snapshots = history.filter(s => s.total_value != null);
    if (snapshots.length < 2) return null;
    const latest   = snapshots[snapshots.length - 1].total_value as number;
    const previous = snapshots[snapshots.length - 2].total_value as number;
    return { amount: latest - previous, pct: ((latest - previous) / previous) * 100 };
  }, [history]);

  const pnlPositive = (todayPnl?.amount ?? 0) >= 0;
  const chartColor  = pnlPositive ? "#00e676" : "#ff5252";
  const gradientId  = `heroGradient-${market}`;

  if (!isLoggedIn) return <NotLoggedIn />;
  if (loading)     return <Skeleton />;

  const totalValue = balance?.total_value ?? null;
  const cash       = balance?.cash ?? null;

  return (
    <div className="bg-[#0f0f1a] border-b border-[#2e2e50] px-6 pt-6 pb-4">
      {/* Total value */}
      <p className="text-xs text-[#555570] uppercase tracking-wide mb-1">Total Portfolio Value</p>
      <p className="text-4xl font-bold text-white mb-1">
        {totalValue != null ? formatValue(totalValue, market) : "—"}
      </p>

      {/* P&L row */}
      <div className="flex items-center gap-1.5 mb-4 text-sm">
        {todayPnl != null ? (
          <>
            <span style={{ color: chartColor }} className="font-semibold">
              {pnlPositive ? "▲" : "▼"}{" "}
              {formatValue(Math.abs(todayPnl.amount), market)}
            </span>
            <span style={{ color: chartColor }} className="font-semibold">
              ({pnlPositive ? "+" : ""}{todayPnl.pct.toFixed(2)}%)
            </span>
            <span className="text-[#555570]">Today</span>
          </>
        ) : (
          <span className="text-[#555570]">— Today</span>
        )}
      </div>

      {/* Area chart */}
      {filteredHistory.length > 1 ? (
        <div className="mb-3" style={{ height: 128 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={filteredHistory} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={chartColor} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={chartColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="transparent" />
              <XAxis
                dataKey="date"
                tick={{ fill: "#555570", fontSize: 9 }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis hide />
              <Tooltip content={<CustomTooltip market={market} />} />
              <Area
                type="monotone"
                dataKey="value"
                stroke={chartColor}
                strokeWidth={2}
                fill={`url(#${gradientId})`}
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-32 flex items-center justify-center text-[#555570] text-xs mb-3 bg-[#111128] rounded-xl border border-[#2e2e50]">
          No history data for this period
        </div>
      )}

      {/* Period pills */}
      <div className="flex gap-2 mb-4">
        {PERIODS.map(p => (
          <button
            key={p}
            onClick={() => setActivePeriod(p)}
            className={[
              "text-xs font-semibold px-3 py-1 rounded-full transition-colors",
              activePeriod === p
                ? "bg-white text-black"
                : "text-[#8888aa] hover:text-white",
            ].join(" ")}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Buying power row */}
      <div className="flex justify-between items-center border-t border-[#2e2e50] pt-3 mt-3">
        <span className="text-sm text-[#8888aa]">Buying Power</span>
        <span className="text-sm font-semibold text-white">
          {cash != null ? formatValue(cash, market) : "—"}
        </span>
      </div>
    </div>
  );
}

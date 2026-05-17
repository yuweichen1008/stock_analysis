"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { BrokerStatus, BrokerBalance, Position, BrokerOrder, TradeRow, AccountSnapshot, OptionsContract, OptionsChainResponse } from "@/lib/types";
import {
  brokerStatus, brokerBalance, brokerPositions, brokerOrders,
  brokerTrades, brokerPlaceOrder, brokerAssetHistory, brokerOptionsChain,
} from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, decimals = 0): string {
  if (n == null) return "—";
  return n.toLocaleString("zh-TW", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-TW", {
    month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function pnlClass(n: number | null | undefined): string {
  if (n == null) return "text-[#8888aa]";
  return n >= 0 ? "text-[#00e676]" : "text-[#ff5252]";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Skeleton({ w = "w-20", h = "h-4" }: { w?: string; h?: string }) {
  return <div className={`${w} ${h} bg-[#1e1e38] rounded animate-pulse`} />;
}

function StatusBadge({ status }: { status: BrokerStatus | null; loading: boolean }) {
  if (!status) return <span className="text-xs text-[#555570]">—</span>;
  if (status.dry_run) {
    return (
      <span className="text-xs font-bold px-2 py-0.5 rounded-full border border-yellow-500 text-yellow-400 bg-yellow-500/10">
        ⚠ DRY RUN
      </span>
    );
  }
  return (
    <span className="text-xs font-bold px-2 py-0.5 rounded-full border border-[#00e676] text-[#00e676] bg-[#00e676]/10">
      ● LIVE
    </span>
  );
}

function AccountBar({
  balance, status, loading, onRefresh, market = "TW",
}: {
  balance: BrokerBalance | null;
  status:  BrokerStatus  | null;
  loading: boolean;
  onRefresh: () => void;
  market?: string;
}) {
  const ccy = balance?.currency === "USD" ? "US$" : "NT$";
  const broker = market === "US" ? "Moomoo" : "CTBC";
  return (
    <div className="flex flex-wrap items-center gap-6 px-4 py-3 bg-[#111128] border-b border-[#2e2e50] text-sm">
      <div>
        <span className="text-[#8888aa]">Cash </span>
        {loading ? <Skeleton /> : (
          <span className="font-bold text-white">
            {balance ? `${ccy} ${fmt(balance.cash)}` : "—"}
          </span>
        )}
      </div>
      <div>
        <span className="text-[#8888aa]">Total Value </span>
        {loading ? <Skeleton /> : (
          <span className="font-bold text-white">
            {balance ? `${ccy} ${fmt(balance.total_value)}` : "—"}
          </span>
        )}
      </div>
      <div>
        <span className="text-[#8888aa]">Unrealized P&L </span>
        {loading ? <Skeleton /> : (
          <span className={`font-bold ${pnlClass(balance?.unrealized_pnl)}`}>
            {balance ? `${ccy} ${fmt(balance.unrealized_pnl)}` : "—"}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[#8888aa]">{broker}</span>
        <StatusBadge status={status} loading={loading} />
      </div>
      <button
        onClick={onRefresh}
        className="ml-auto text-xs px-3 py-1.5 rounded-lg bg-[#1a1a2e] text-[#8888aa] hover:text-white border border-[#2e2e50] hover:border-[#4e4e70] transition-colors"
      >
        ↻ Refresh
      </button>
    </div>
  );
}

function PositionsTable({ positions, loading }: { positions: Position[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {[...Array(3)].map((_, i) => <Skeleton key={i} w="w-full" h="h-8" />)}
      </div>
    );
  }
  if (!positions.length) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-[#555570]">
        <span className="text-3xl mb-2">📭</span>
        <span className="text-sm">No open positions</span>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#2e2e50] text-[#555570] text-xs">
            <th className="text-left px-3 py-2">Ticker</th>
            <th className="text-right px-3 py-2">Qty</th>
            <th className="text-right px-3 py-2">Avg Cost</th>
            <th className="text-right px-3 py-2">Mkt Value</th>
            <th className="text-right px-3 py-2">P&L</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p, i) => {
            const pnlPct = p.avg_cost > 0 ? ((p.mkt_value / (p.avg_cost * p.qty)) - 1) * 100 : null;
            return (
              <tr key={i} className="border-b border-[#1e1e38] hover:bg-[#13132a] transition-colors">
                <td className="px-3 py-2 font-bold text-white">{p.ticker}</td>
                <td className="px-3 py-2 text-right text-[#ccc]">{fmt(p.qty)}</td>
                <td className="px-3 py-2 text-right text-[#ccc]">{fmt(p.avg_cost, 2)}</td>
                <td className="px-3 py-2 text-right text-[#ccc]">NT$ {fmt(p.mkt_value)}</td>
                <td className={`px-3 py-2 text-right font-bold ${pnlClass(p.pnl)}`}>
                  {fmt(p.pnl)} <span className="text-xs opacity-70">({fmtPct(pnlPct)})</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function OrderForm({
  onOrderPlaced,
  market = "TW",
  prefillTicker = "",
  prefillPrice  = "",
  onClearPrefill,
}: {
  onOrderPlaced:  (msg: string, isDry: boolean) => void;
  market?:        string;
  prefillTicker?: string;
  prefillPrice?:  string;
  onClearPrefill?: () => void;
}) {
  const [ticker,     setTicker]     = useState(prefillTicker);
  const [side,       setSide]       = useState<"buy" | "sell">("buy");
  const [qty,        setQty]        = useState("");
  const [price,      setPrice]      = useState(prefillPrice);

  useEffect(() => {
    if (prefillTicker) setTicker(prefillTicker);
    if (prefillPrice)  setPrice(prefillPrice);
  }, [prefillTicker, prefillPrice]);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticker || !qty || !price) return;
    setConfirming(true);
  };

  const handleConfirm = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await brokerPlaceOrder({
        ticker:       ticker.toUpperCase(),
        side,
        qty:          parseFloat(qty),
        limit_price:  parseFloat(price),
        market,
        signal_source: "manual",
      });
      setConfirming(false);
      setTicker(""); setQty(""); setPrice("");
      onClearPrefill?.();
      onOrderPlaced(result.message, result.dry_run);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Order failed");
      setConfirming(false);
    } finally {
      setSubmitting(false);
    }
  };

  if (confirming) {
    return (
      <div className="p-4 space-y-4">
        <div className="p-3 rounded-lg bg-[#1a1a2e] border border-[#2e2e50] text-sm">
          <p className="text-[#8888aa] mb-2">Confirm order:</p>
          <p className="text-white font-bold text-base">
            {side.toUpperCase()} {parseInt(qty).toLocaleString()} shares
          </p>
          <p className="text-white">{ticker.toUpperCase()} @ NT$ {parseFloat(price).toLocaleString()}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleConfirm}
            disabled={submitting}
            className={`flex-1 py-2 rounded-lg font-bold text-sm transition-colors ${
              side === "buy"
                ? "bg-[#00e676] text-black hover:bg-[#00c853]"
                : "bg-[#ff5252] text-white hover:bg-[#ff1744]"
            } disabled:opacity-50`}
          >
            {submitting ? "Submitting…" : `Confirm ${side.toUpperCase()}`}
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="px-4 py-2 rounded-lg bg-[#1a1a2e] text-[#8888aa] hover:text-white border border-[#2e2e50] text-sm transition-colors"
          >
            Cancel
          </button>
        </div>
        {error && <p className="text-xs text-[#ff5252]">{error}</p>}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-3">
      <div>
        <label className="text-xs text-[#8888aa] block mb-1">Stock Code (台股代號)</label>
        <input
          value={ticker}
          onChange={e => setTicker(e.target.value.toUpperCase())}
          placeholder="e.g. 2330"
          maxLength={10}
          className="w-full bg-[#0d0d14] border border-[#2e2e50] rounded-lg px-3 py-2 text-white text-sm placeholder-[#555570] focus:outline-none focus:border-[#4e4e90]"
        />
      </div>
      <div>
        <label className="text-xs text-[#8888aa] block mb-1">Side</label>
        <div className="flex gap-2">
          {(["buy", "sell"] as const).map(s => (
            <button
              key={s}
              type="button"
              onClick={() => setSide(s)}
              className={`flex-1 py-2 rounded-lg text-sm font-bold transition-colors border ${
                side === s
                  ? s === "buy"
                    ? "bg-[#00e676]/20 border-[#00e676] text-[#00e676]"
                    : "bg-[#ff5252]/20 border-[#ff5252] text-[#ff5252]"
                  : "bg-transparent border-[#2e2e50] text-[#555570]"
              }`}
            >
              {s === "buy" ? "🟢 Buy" : "🔴 Sell"}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="text-xs text-[#8888aa] block mb-1">Qty (shares / 股數)</label>
        <input
          type="number"
          value={qty}
          onChange={e => setQty(e.target.value)}
          placeholder="1000"
          min={1}
          step={1}
          className="w-full bg-[#0d0d14] border border-[#2e2e50] rounded-lg px-3 py-2 text-white text-sm placeholder-[#555570] focus:outline-none focus:border-[#4e4e90]"
        />
      </div>
      <div>
        <label className="text-xs text-[#8888aa] block mb-1">Limit Price (NT$)</label>
        <input
          type="number"
          value={price}
          onChange={e => setPrice(e.target.value)}
          placeholder="950.00"
          min={0.01}
          step={0.01}
          className="w-full bg-[#0d0d14] border border-[#2e2e50] rounded-lg px-3 py-2 text-white text-sm placeholder-[#555570] focus:outline-none focus:border-[#4e4e90]"
        />
      </div>
      {error && <p className="text-xs text-[#ff5252]">{error}</p>}
      <button
        type="submit"
        disabled={!ticker || !qty || !price}
        className={`w-full py-2.5 rounded-lg font-bold text-sm transition-colors ${
          side === "buy"
            ? "bg-[#00e676] text-black hover:bg-[#00c853] disabled:bg-[#00e676]/30 disabled:text-black/40"
            : "bg-[#ff5252] text-white hover:bg-[#ff1744] disabled:bg-[#ff5252]/30 disabled:text-white/40"
        }`}
      >
        Place {side.toUpperCase()} Order
      </button>
      <p className="text-xs text-[#555570]">
        LIMIT orders only · {market === "US" ? "Moomoo OpenD" : "CTBC Win168"}
      </p>
    </form>
  );
}

function TodayOrders({ orders, loading }: { orders: BrokerOrder[]; loading: boolean }) {
  if (loading) return <div className="p-4"><Skeleton w="w-full" h="h-16" /></div>;
  if (!orders.length) {
    return <p className="text-xs text-[#555570] px-4 py-3">No orders today</p>;
  }
  return (
    <div className="divide-y divide-[#1e1e38]">
      {orders.slice(0, 10).map((o, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-2 text-xs">
          <span className={`font-bold ${o.side === "BUY" ? "text-[#00e676]" : "text-[#ff5252]"}`}>
            {o.side}
          </span>
          <span className="font-bold text-white">{o.ticker}</span>
          <span className="text-[#8888aa]">{fmt(o.qty)} × {fmt(o.price, 2)}</span>
          <span className="ml-auto text-[#555570]">{o.status}</span>
        </div>
      ))}
    </div>
  );
}

function TradeHistory({ trades, loading }: { trades: TradeRow[]; loading: boolean }) {
  const [filter, setFilter] = useState<"all" | "buy" | "sell">("all");
  const [page,   setPage]   = useState(0);
  const PER_PAGE = 20;

  const filtered = trades.filter(t => filter === "all" || t.side === filter);
  const totalPages = Math.ceil(filtered.length / PER_PAGE);
  const paged = filtered.slice(page * PER_PAGE, (page + 1) * PER_PAGE);

  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {[...Array(5)].map((_, i) => <Skeleton key={i} w="w-full" h="h-8" />)}
      </div>
    );
  }

  return (
    <div>
      {/* Filters */}
      <div className="flex gap-2 px-4 py-2 border-b border-[#2e2e50]">
        {(["all", "buy", "sell"] as const).map(f => (
          <button
            key={f}
            onClick={() => { setFilter(f); setPage(0); }}
            className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
              filter === f
                ? "bg-[#4e4e90]/30 border-[#4e4e90] text-white"
                : "border-[#2e2e50] text-[#555570] hover:text-white"
            }`}
          >
            {f === "all" ? "All" : f === "buy" ? "🟢 Buy" : "🔴 Sell"}
          </button>
        ))}
        <span className="ml-auto text-xs text-[#555570] self-center">{filtered.length} trades</span>
      </div>

      {!paged.length ? (
        <div className="flex flex-col items-center py-10 text-[#555570]">
          <span className="text-3xl mb-2">📋</span>
          <span className="text-sm">No trade history yet</span>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#2e2e50] text-[#555570]">
                  <th className="text-left px-3 py-2">Date</th>
                  <th className="text-left px-3 py-2">Ticker</th>
                  <th className="text-left px-3 py-2">Side</th>
                  <th className="text-right px-3 py-2">Qty</th>
                  <th className="text-right px-3 py-2">Price</th>
                  <th className="text-right px-3 py-2">P&L</th>
                  <th className="text-right px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {paged.map(t => (
                  <tr key={t.id} className="border-b border-[#1e1e38] hover:bg-[#13132a] transition-colors">
                    <td className="px-3 py-2 text-[#8888aa]">{fmtDate(t.executed_at || t.created_at)}</td>
                    <td className="px-3 py-2 font-bold text-white">{t.ticker}</td>
                    <td className="px-3 py-2">
                      <span className={`font-bold ${t.side === "buy" ? "text-[#00e676]" : "text-[#ff5252]"}`}>
                        {t.side.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-[#ccc]">{fmt(t.qty)}</td>
                    <td className="px-3 py-2 text-right text-[#ccc]">
                      {t.filled_price ? fmt(t.filled_price, 2) : t.limit_price ? fmt(t.limit_price, 2) : "—"}
                    </td>
                    <td className={`px-3 py-2 text-right font-bold ${pnlClass(t.realized_pnl)}`}>
                      {t.realized_pnl != null ? fmt(t.realized_pnl) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <StatusPill status={t.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 px-4 py-2 border-t border-[#2e2e50] text-xs text-[#8888aa]">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="hover:text-white disabled:opacity-30"
              >
                ← Prev
              </button>
              <span>Page {page + 1} of {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="hover:text-white disabled:opacity-30"
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: TradeRow["status"] }) {
  const map: Record<string, [string, string]> = {
    pending:   ["#ffd740", "rgba(255,215,64,0.1)"],
    filled:    ["#00e676", "rgba(0,230,118,0.1)"],
    cancelled: ["#8888aa", "rgba(136,136,170,0.1)"],
    rejected:  ["#ff5252", "rgba(255,82,82,0.1)"],
  };
  const [color, bg] = map[status] ?? ["#8888aa", "transparent"];
  return (
    <span
      className="text-xs px-1.5 py-0.5 rounded border capitalize"
      style={{ color, borderColor: color, backgroundColor: bg }}
    >
      {status}
    </span>
  );
}

// ── Asset history chart ───────────────────────────────────────────────────────

function AssetHistoryChart({ history, market }: { history: AccountSnapshot[]; market: string }) {
  const ccy = market === "US" ? "US$" : "NT$";
  if (!history.length) {
    return (
      <div className="flex items-center justify-center h-24 text-[#555570] text-xs">
        No history yet — opens automatically as you use the platform
      </div>
    );
  }
  const data = history.map(h => ({
    date:  h.date?.slice(5) ?? "",   // MM-DD
    value: h.total_value ?? 0,
  }));
  const min = Math.min(...data.map(d => d.value));
  const max = Math.max(...data.map(d => d.value));
  const domain: [number, number] = [Math.floor(min * 0.995), Math.ceil(max * 1.005)];
  const latest = data[data.length - 1]?.value ?? 0;
  const first  = data[0]?.value ?? 0;
  const delta  = latest - first;
  const deltaPct = first > 0 ? (delta / first) * 100 : 0;
  const color = delta >= 0 ? "#00e676" : "#ff5252";

  return (
    <div className="px-4 py-3 border-b border-[#2e2e50]">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-[#8888aa]">Asset History ({history.length}d)</span>
        <span className={`text-xs font-bold ${delta >= 0 ? "text-[#00e676]" : "text-[#ff5252]"}`}>
          {delta >= 0 ? "+" : ""}{ccy} {fmt(delta)} ({deltaPct >= 0 ? "+" : ""}{deltaPct.toFixed(2)}%)
        </span>
      </div>
      <ResponsiveContainer width="100%" height={72}>
        <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="assetGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#555570" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis domain={domain} hide />
          <Tooltip
            contentStyle={{ background: "#111128", border: "1px solid #2e2e50", borderRadius: 6, fontSize: 11 }}
            formatter={(v: number) => [`${ccy} ${v.toLocaleString()}`, "Total Value"]}
            labelStyle={{ color: "#8888aa" }}
          />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} fill="url(#assetGrad)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Options chain panel ───────────────────────────────────────────────────────

function OptionsChainPanel({ onSelectContract }: {
  onSelectContract: (code: string, price: number) => void;
}) {
  const [ticker,    setTicker]    = useState("AAPL");
  const [chain,     setChain]     = useState<OptionsChainResponse | null>(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<"ALL" | "CALL" | "PUT">("ALL");

  const fetchChain = async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const res = await brokerOptionsChain(ticker);
      setChain(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch options chain");
    } finally {
      setLoading(false);
    }
  };

  const contracts = (chain?.contracts ?? []).filter(
    c => typeFilter === "ALL" || c.type === typeFilter
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Search bar */}
      <div className="flex gap-2 p-3 border-b border-[#2e2e50]">
        <input
          value={ticker}
          onChange={e => setTicker(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === "Enter" && fetchChain()}
          placeholder="AAPL"
          className="flex-1 bg-[#0d0d14] border border-[#2e2e50] rounded-lg px-3 py-1.5 text-white text-sm placeholder-[#555570] focus:outline-none focus:border-[#4e4e90]"
        />
        <button
          onClick={fetchChain}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg bg-[#1a2744] text-[#448aff] border border-[#448aff]/40 text-sm font-bold hover:bg-[#243380] transition-colors disabled:opacity-40"
        >
          {loading ? "…" : "Fetch"}
        </button>
      </div>

      {error && <p className="text-xs text-[#ff5252] px-3 py-2">{error}</p>}

      {chain && (
        <div className="px-3 py-1.5 border-b border-[#2e2e50] flex items-center gap-2">
          <span className="text-xs text-[#8888aa]">Expiry: {chain.expiry ?? "—"}</span>
          <span className="text-xs text-[#555570]">|</span>
          {(["ALL", "CALL", "PUT"] as const).map(t => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                typeFilter === t
                  ? t === "CALL" ? "border-[#00e676] text-[#00e676] bg-[#00e676]/10"
                  : t === "PUT"  ? "border-[#ff5252] text-[#ff5252] bg-[#ff5252]/10"
                  : "border-[#4e4e90] text-white bg-[#1a1a2e]"
                  : "border-[#2e2e50] text-[#555570]"
              }`}
            >
              {t}
            </button>
          ))}
          <span className="ml-auto text-xs text-[#555570]">{contracts.length} contracts</span>
        </div>
      )}

      {!chain && !loading && (
        <div className="flex flex-col items-center justify-center flex-1 text-[#555570] text-xs gap-1">
          <span className="text-2xl">⛓</span>
          <span>Enter a US ticker and click Fetch</span>
          <span className="text-[#2e2e50]">Requires Moomoo OpenD running</span>
        </div>
      )}

      {chain && (
        <div className="flex-1 overflow-y-auto text-xs">
          <table className="w-full">
            <thead className="sticky top-0 bg-[#0d0d14]">
              <tr className="border-b border-[#2e2e50] text-[#555570]">
                <th className="text-left px-2 py-1.5">Type</th>
                <th className="text-right px-2 py-1.5">Strike</th>
                <th className="text-right px-2 py-1.5">Bid</th>
                <th className="text-right px-2 py-1.5">Ask</th>
                <th className="text-right px-2 py-1.5">IV%</th>
                <th className="text-right px-2 py-1.5">Δ</th>
                <th className="text-right px-2 py-1.5">OI</th>
              </tr>
            </thead>
            <tbody>
              {contracts.map((c, i) => (
                <tr
                  key={i}
                  onClick={() => onSelectContract(c.code, c.ask || c.last)}
                  className="border-b border-[#1e1e38] hover:bg-[#13132a] cursor-pointer transition-colors"
                >
                  <td className={`px-2 py-1.5 font-bold ${c.type === "CALL" ? "text-[#00e676]" : "text-[#ff5252]"}`}>
                    {c.type}
                  </td>
                  <td className="px-2 py-1.5 text-right text-white">{c.strike.toFixed(0)}</td>
                  <td className="px-2 py-1.5 text-right text-[#ccc]">{c.bid.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right text-[#ccc]">{c.ask.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right text-[#8888aa]">{(c.iv * 100).toFixed(0)}%</td>
                  <td className="px-2 py-1.5 text-right text-[#8888aa]">{c.delta.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right text-[#555570]">{c.open_int.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TradingPage() {
  const { user } = useAuth();
  const [market,    setMarket]    = useState<"TW" | "US">("TW");
  const [status,    setStatus]    = useState<BrokerStatus  | null>(null);
  const [balance,   setBalance]   = useState<BrokerBalance | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders,    setOrders]    = useState<BrokerOrder[]>([]);
  const [trades,    setTrades]    = useState<TradeRow[]>([]);
  const [history,   setHistory]   = useState<AccountSnapshot[]>([]);

  const [loadingAccount,   setLoadingAccount]   = useState(true);
  const [loadingPositions, setLoadingPositions] = useState(true);
  const [loadingOrders,    setLoadingOrders]    = useState(true);
  const [loadingTrades,    setLoadingTrades]    = useState(true);

  const [rightTab, setRightTab] = useState<"order" | "options">("order");
  const [orderTicker, setOrderTicker] = useState("");
  const [orderPrice,  setOrderPrice]  = useState("");

  const [toast, setToast] = useState<{ msg: string; dry: boolean } | null>(null);

  const loadAccount = useCallback(async (mkt: string) => {
    setLoadingAccount(true);
    try {
      const [st, bal] = await Promise.allSettled([brokerStatus(), brokerBalance(mkt)]);
      if (st.status  === "fulfilled") setStatus(st.value);
      if (bal.status === "fulfilled") setBalance(bal.value);
    } finally {
      setLoadingAccount(false);
    }
  }, []);

  const loadPositions = useCallback(async (mkt: string) => {
    setLoadingPositions(true);
    try {
      setPositions(await brokerPositions(mkt));
    } catch {
      setPositions([]);
    } finally {
      setLoadingPositions(false);
    }
  }, []);

  const loadOrders = useCallback(async (mkt: string) => {
    setLoadingOrders(true);
    try {
      setOrders(await brokerOrders(1, mkt));
    } catch {
      setOrders([]);
    } finally {
      setLoadingOrders(false);
    }
  }, []);

  const loadTrades = useCallback(async (mkt: string) => {
    setLoadingTrades(true);
    try {
      setTrades(await brokerTrades({ limit: 200, days: 90, market: mkt }));
    } catch {
      setTrades([]);
    } finally {
      setLoadingTrades(false);
    }
  }, []);

  const loadHistory = useCallback(async (mkt: string) => {
    brokerAssetHistory(mkt, 90).then(setHistory).catch(() => {});
  }, []);

  const refresh = useCallback((mkt: string) => {
    loadAccount(mkt);
    loadPositions(mkt);
    loadOrders(mkt);
    loadTrades(mkt);
    loadHistory(mkt);
  }, [loadAccount, loadPositions, loadOrders, loadTrades, loadHistory]);

  useEffect(() => { refresh(market); }, [market]);  // eslint-disable-line react-hooks/exhaustive-deps

  const handleOrderPlaced = (msg: string, isDry: boolean) => {
    setToast({ msg, dry: isDry });
    setTimeout(() => setToast(null), 6000);
    loadPositions(market);
    loadTrades(market);
    loadOrders(market);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-16 right-4 z-50 max-w-sm p-3 rounded-lg border text-sm shadow-lg ${
          toast.dry
            ? "bg-[#1a1a2e] border-yellow-500 text-yellow-300"
            : "bg-[#1a1a2e] border-[#00e676] text-[#00e676]"
        }`}>
          {toast.dry && <span className="font-bold">DRY RUN — </span>}
          {toast.msg}
        </div>
      )}

      {/* Login banner */}
      {!user && (
        <div className="shrink-0 px-4 py-2 bg-[#7c5cfc1a] border-b border-[#7c5cfc40] flex items-center justify-between">
          <span className="text-xs text-[#a99cff]">
            Sign in to connect your broker and place live orders
          </span>
          <Link href="/login?next=/trading" className="text-xs font-semibold text-[#7c5cfc] hover:text-[#8f72ff] whitespace-nowrap ml-3">
            Sign In →
          </Link>
        </div>
      )}

      {/* Market toggle + Account bar */}
      <div className="shrink-0">
        <div className="flex items-center gap-2 px-4 py-2 bg-[#0d0d14] border-b border-[#2e2e50]">
          <span className="text-xs text-[#555570]">市場</span>
          {(["TW", "US"] as const).map(m => (
            <button
              key={m}
              onClick={() => setMarket(m)}
              className={[
                "text-xs font-bold px-3 py-1 rounded-lg border transition-colors",
                market === m
                  ? "border-[#448aff] text-[#448aff] bg-[#1a2744]"
                  : "border-[#2e2e50] text-[#555570] hover:border-[#448aff] hover:text-[#448aff]",
              ].join(" ")}
            >
              {m === "TW" ? "🇹🇼 CTBC" : "🇺🇸 Moomoo"}
            </button>
          ))}
          {market === "US" && (
            <span className="text-[10px] text-[#555570] ml-1">需要 Moomoo OpenD 執行中</span>
          )}
        </div>
        <AccountBar
          balance={balance}
          status={status}
          loading={loadingAccount}
          onRefresh={() => refresh(market)}
          market={market}
        />
      </div>

      {/* Asset history chart */}
      <div className="shrink-0 bg-[#111128]">
        <AssetHistoryChart history={history} market={market} />
      </div>

      {/* Main layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: positions + trade history */}
        <div className="flex-1 flex flex-col overflow-hidden border-r border-[#2e2e50]">
          {/* Positions */}
          <div className="shrink-0">
            <div className="px-4 py-2 border-b border-[#2e2e50] flex items-center gap-2">
              <h2 className="text-sm font-bold text-white">Open Positions</h2>
              <span className="text-xs text-[#555570]">{positions.length} holdings</span>
            </div>
            <PositionsTable positions={positions} loading={loadingPositions} />
          </div>

          {/* Trade history */}
          <div className="flex-1 flex flex-col overflow-hidden border-t border-[#2e2e50]">
            <div className="px-4 py-2 border-b border-[#2e2e50]">
              <h2 className="text-sm font-bold text-white">Trade History</h2>
            </div>
            <div className="flex-1 overflow-y-auto">
              <TradeHistory trades={trades} loading={loadingTrades} />
            </div>
          </div>
        </div>

        {/* Right: order form / options chain + today's orders */}
        <div className="w-80 shrink-0 flex flex-col overflow-hidden">
          {/* Tab switcher */}
          <div className="shrink-0 border-b border-[#2e2e50] flex">
            {([
              ["order",   "Place Order"],
              ["options", "Options Chain"],
            ] as const).map(([tab, label]) => (
              <button
                key={tab}
                onClick={() => setRightTab(tab)}
                className={[
                  "flex-1 py-2 text-xs font-bold border-b-2 transition-colors",
                  rightTab === tab
                    ? "border-[#448aff] text-white"
                    : "border-transparent text-[#555570] hover:text-white",
                ].join(" ")}
              >
                {label}
              </button>
            ))}
          </div>

          {rightTab === "order" ? (
            <>
              <div className="shrink-0 border-b border-[#2e2e50]">
                <OrderForm
                  onOrderPlaced={handleOrderPlaced}
                  market={market}
                  prefillTicker={orderTicker}
                  prefillPrice={orderPrice}
                  onClearPrefill={() => { setOrderTicker(""); setOrderPrice(""); }}
                />
              </div>
              <div className="flex-1 overflow-y-auto">
                <div className="px-4 py-2 border-b border-[#2e2e50]">
                  <h2 className="text-xs font-bold text-[#8888aa] uppercase tracking-wide">Today&apos;s Orders</h2>
                </div>
                <TodayOrders orders={orders} loading={loadingOrders} />
              </div>
            </>
          ) : (
            <div className="flex-1 overflow-hidden flex flex-col">
              <OptionsChainPanel
                onSelectContract={(code, price) => {
                  setOrderTicker(code);
                  setOrderPrice(String(price));
                  setRightTab("order");
                }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

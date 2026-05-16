"use client";

import { useEffect, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { OptionsBacktestResult, SignalsBacktestResult, OptionsBtGroup } from "@/lib/types";
import { backtestOptions, backtestSignals } from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function pct(v: number) {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function colorForRate(rate: number) {
  if (rate >= 60) return "#00e676";
  if (rate >= 50) return "#ffd740";
  return "#ff8a65";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-28 bg-[#1a1a2e] rounded-xl" />
      <div className="h-28 bg-[#1a1a2e] rounded-xl" />
    </div>
  );
}

function StatCard({ label, value, color, sub }: {
  label: string; value: string; color?: string; sub?: string;
}) {
  return (
    <div className="bg-[#0d0d14] border border-[#2e2e50] rounded-xl p-3">
      <p className="text-[10px] text-[#555570] uppercase tracking-wide mb-1">{label}</p>
      <p className="text-base font-bold" style={{ color: color ?? "white" }}>{value}</p>
      {sub && <p className="text-[10px] text-[#8888aa] mt-0.5">{sub}</p>}
    </div>
  );
}

function OptionsBtCard({ label, icon, result }: {
  label: string; icon: string; result: OptionsBtGroup | undefined;
}) {
  if (!result) return (
    <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4">
      <p className="text-xs font-bold text-[#8888aa] uppercase mb-2">{icon} {label}</p>
      <p className="text-[#555570] text-sm">No trades found</p>
    </div>
  );

  const wr = result.win_rate_pct;
  const color = colorForRate(wr);

  return (
    <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-bold text-[#8888aa] uppercase">{icon} {label}</p>
        <span className="text-[10px] text-[#555570]">{result.trades} trades</span>
      </div>

      {/* Win-rate bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs mb-1">
          <span style={{ color }}>Win Rate</span>
          <span className="font-extrabold" style={{ color }}>{wr.toFixed(1)}%</span>
        </div>
        <div className="h-2 bg-[#2e2e50] rounded-full overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${wr}%`, backgroundColor: color }} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-[10px] text-[#555570]">W / L</p>
          <p className="text-xs font-bold text-white">{result.wins} / {result.losses}</p>
        </div>
        <div>
          <p className="text-[10px] text-[#555570]">Avg Return</p>
          <p className={`text-xs font-bold ${result.avg_return_pct >= 0 ? "text-[#00e676]" : "text-[#ff5252]"}`}>
            {pct(result.avg_return_pct)}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-[#555570]">Sharpe</p>
          <p className="text-xs font-bold text-white">{result.sharpe?.toFixed(2) ?? "—"}</p>
        </div>
      </div>
    </div>
  );
}

// ── Equity curve tooltip ──────────────────────────────────────────────────────

function EquityTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-lg px-3 py-2 text-xs">
      <p className="text-[#8888aa] mb-0.5">{d.date}</p>
      <p className="font-bold text-[#00e676]">NT${d.equity.toLocaleString()}</p>
    </div>
  );
}

// ── Signals backtest params form ──────────────────────────────────────────────

interface SbtParams {
  start_date:      string;
  end_date:        string;
  holding_days:    number;
  stop_loss_pct:   number;
  take_profit_pct: number;
  max_tickers:     number;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BacktestPage() {
  const [optData,    setOptData]    = useState<OptionsBacktestResult | null>(null);
  const [optLoading, setOptLoading] = useState(true);

  const [sigData,    setSigData]    = useState<SignalsBacktestResult | null>(null);
  const [sigLoading, setSigLoading] = useState(false);

  const [params, setParams] = useState<SbtParams>({
    start_date:      "2024-01-01",
    end_date:        "2026-01-01",
    holding_days:    5,
    stop_loss_pct:   0.05,
    take_profit_pct: 0.10,
    max_tickers:     30,
  });

  // Load options backtest on mount
  useEffect(() => {
    backtestOptions()
      .then(setOptData)
      .catch(() => setOptData({ error: "Failed to load options backtest" }))
      .finally(() => setOptLoading(false));
  }, []);

  const runSignalsBt = async () => {
    setSigLoading(true);
    setSigData(null);
    try {
      const result = await backtestSignals(params);
      setSigData(result);
    } catch (e: unknown) {
      setSigData({ error: e instanceof Error ? e.message : "Failed", summary: null as any, trades: [], equity_curve: [], tickers_tested: 0 });
    } finally {
      setSigLoading(false);
    }
  };

  const set = (k: keyof SbtParams, v: string | number) =>
    setParams(prev => ({ ...prev, [k]: v }));

  const sigsummary = sigData?.summary;
  const eqCurve    = sigData?.equity_curve ?? [];

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="flex-1 p-6 max-w-screen-2xl mx-auto w-full">
        <div className="mb-6">
          <h1 className="text-2xl font-extrabold text-white mb-1">🔬 Backtesting Lab</h1>
          <p className="text-sm text-[#8888aa]">Validate signal strategies against historical data before trading with real capital.</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* ── LEFT: Options RSI+PCR backtest ───────────────────────── */}
          <section className="flex flex-col gap-4">
            <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4">
              <h2 className="text-sm font-bold text-white uppercase tracking-wide mb-1">
                📈 Options RSI + PCR Strategy
              </h2>
              <p className="text-xs text-[#8888aa] mb-4">
                Validates buy/sell signals against weekly stock returns from the signal history database.
                Uses RSI proxy from weekly return percentage + put/call ratio.
              </p>

              {optLoading && <Skeleton />}

              {!optLoading && optData?.error && (
                <div className="bg-[#0d0d14] border border-[#2e2e50] rounded-xl p-4 text-xs text-[#8888aa]">
                  <p className="text-[#ff8a65] font-bold mb-1">No backtest data</p>
                  <p>{optData.error}</p>
                  <p className="mt-2">Run the weekly signal pipeline to populate history:</p>
                  <pre className="mt-1 text-[#00e676] font-mono">WEEKLY_DRY_RUN=true python weekly_signal_pipeline.py</pre>
                </div>
              )}

              {!optLoading && optData && !optData.error && (
                <div className="space-y-3">
                  <OptionsBtCard label="Buy Signal" icon="🟢" result={optData.buy_signal} />
                  <OptionsBtCard label="Sell Signal" icon="🔴" result={optData.sell_signal} />
                  <OptionsBtCard label="Combined" icon="⚡" result={optData.combined} />

                  {optData.combined && optData.combined.trades > 0 && (
                    <div className="grid grid-cols-2 gap-2">
                      <StatCard
                        label="Overall Win Rate"
                        value={`${optData.combined.win_rate_pct.toFixed(1)}%`}
                        color={colorForRate(optData.combined.win_rate_pct)}
                      />
                      <StatCard
                        label="Combined Sharpe"
                        value={optData.combined.sharpe?.toFixed(2) ?? "—"}
                        color={
                          (optData.combined.sharpe ?? 0) >= 1 ? "#00e676"
                          : (optData.combined.sharpe ?? 0) >= 0 ? "#ffd740"
                          : "#ff5252"
                        }
                      />
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Legend / methodology note */}
            <div className="bg-[#111128] border border-[#2e2e50] rounded-xl p-4 text-xs text-[#555570] space-y-1">
              <p className="text-[#8888aa] font-bold mb-2">How it works</p>
              <p>• <span className="text-white">Buy signal</span>: RSI proxy &lt; 40 AND PCR &gt; 1.0 → expects next-week positive return</p>
              <p>• <span className="text-white">Sell signal</span>: RSI proxy &gt; 60 AND PCR &lt; 0.6 → expects next-week negative return</p>
              <p>• RSI proxy is estimated from weekly return: clamp(50 + return% × 200, 0, 100)</p>
              <p>• Win = next week's return is in the predicted direction</p>
            </div>
          </section>

          {/* ── RIGHT: TWS signal backtest ───────────────────────────── */}
          <section className="flex flex-col gap-4">
            <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4">
              <h2 className="text-sm font-bold text-white uppercase tracking-wide mb-1">
                📊 TWS Mean-Reversion Signals
              </h2>
              <p className="text-xs text-[#8888aa] mb-4">
                Backtests the TAIEX signal strategy on locally cached OHLCV data.
                Entry on signal fire, exit via stop-loss, take-profit, or time-stop.
              </p>

              {/* Params form */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                {[
                  { label: "Start Date",    key: "start_date",      type: "date",   step: undefined  },
                  { label: "End Date",      key: "end_date",        type: "date",   step: undefined  },
                  { label: "Hold Days",     key: "holding_days",    type: "number", step: 1          },
                  { label: "Stop Loss %",   key: "stop_loss_pct",   type: "number", step: 0.01       },
                  { label: "Take Profit %", key: "take_profit_pct", type: "number", step: 0.01       },
                  { label: "Max Tickers",   key: "max_tickers",     type: "number", step: 1          },
                ].map(({ label, key, type, step }) => (
                  <div key={key}>
                    <label className="text-[10px] text-[#555570] uppercase tracking-wide block mb-1">{label}</label>
                    <input
                      type={type}
                      step={step}
                      value={String(params[key as keyof SbtParams])}
                      onChange={e => set(key as keyof SbtParams,
                        type === "number" ? parseFloat(e.target.value) : e.target.value)}
                      className="w-full bg-[#0d0d14] border border-[#2e2e50] rounded-lg px-2 py-1.5 text-sm text-white focus:outline-none focus:border-[#448aff]"
                    />
                  </div>
                ))}
              </div>

              <button
                onClick={runSignalsBt}
                disabled={sigLoading}
                className="w-full py-2.5 bg-[#448aff] hover:bg-[#6da3ff] disabled:opacity-50 text-white font-bold text-sm rounded-lg transition-colors"
              >
                {sigLoading ? "Running backtest…" : "▶ Run Backtest"}
              </button>
            </div>

            {/* Results */}
            {sigLoading && (
              <div className="animate-pulse space-y-3">
                <div className="h-48 bg-[#1a1a2e] rounded-xl" />
                <div className="h-48 bg-[#1a1a2e] rounded-xl" />
              </div>
            )}

            {sigData?.error && (
              <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4 text-xs">
                <p className="text-[#ff8a65] font-bold mb-1">Backtest error</p>
                <p className="text-[#8888aa]">{sigData.error}</p>
                {sigData.error.includes("No OHLCV") && (
                  <p className="mt-2 text-[#555570]">Download data first: <code className="text-[#00e676]">python tws/core.py</code></p>
                )}
              </div>
            )}

            {sigsummary && !sigData?.error && (
              <>
                {/* Summary stats */}
                <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4">
                  <p className="text-xs font-bold text-[#8888aa] uppercase mb-3">Summary — {sigsummary.total_trades} trades across {sigData?.tickers_tested} tickers</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    <StatCard
                      label="Win Rate"
                      value={`${(sigsummary.win_rate * 100).toFixed(1)}%`}
                      color={colorForRate(sigsummary.win_rate * 100)}
                      sub={`${sigsummary.wins}W / ${sigsummary.losses}L`}
                    />
                    <StatCard
                      label="Avg Net P&L"
                      value={pct(sigsummary.avg_profit_pct)}
                      color={sigsummary.avg_profit_pct >= 0 ? "#00e676" : "#ff5252"}
                    />
                    <StatCard
                      label="Sharpe"
                      value={sigsummary.sharpe.toFixed(2)}
                      color={sigsummary.sharpe >= 1 ? "#00e676" : sigsummary.sharpe >= 0 ? "#ffd740" : "#ff5252"}
                    />
                    <StatCard
                      label="Max Drawdown"
                      value={`${(sigsummary.max_drawdown * 100).toFixed(1)}%`}
                      color={Math.abs(sigsummary.max_drawdown) <= 0.1 ? "#00e676" : "#ff8a65"}
                    />
                    <StatCard label="Stop Loss Exits"    value={String(sigsummary.stop_loss_exits)} />
                    <StatCard label="Take Profit Exits"  value={String(sigsummary.take_profit_exits)} />
                  </div>
                </div>

                {/* Equity curve */}
                {eqCurve.length > 1 && (
                  <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4">
                    <p className="text-xs font-bold text-[#8888aa] uppercase mb-3">Equity Curve (NT$100K start)</p>
                    <ResponsiveContainer width="100%" height={200}>
                      <AreaChart data={eqCurve} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="#00e676" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#00e676" stopOpacity={0.0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e1e38" />
                        <XAxis
                          dataKey="date"
                          tick={{ fill: "#555570", fontSize: 10 }}
                          tickLine={false}
                          axisLine={false}
                          interval={Math.ceil(eqCurve.length / 6)}
                        />
                        <YAxis
                          tick={{ fill: "#8888aa", fontSize: 10 }}
                          tickLine={false}
                          axisLine={false}
                          width={70}
                          tickFormatter={v => `$${(v / 1000).toFixed(0)}K`}
                        />
                        <ReferenceLine y={100_000} stroke="#555570" strokeDasharray="4 2" />
                        <Tooltip content={<EquityTooltip />} />
                        <Area
                          type="monotone"
                          dataKey="equity"
                          stroke="#00e676"
                          strokeWidth={2}
                          fill="url(#eqGrad)"
                          dot={false}
                          isAnimationActive={false}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Trades table */}
                {sigData!.trades.length > 0 && (
                  <div className="bg-[#1a1a2e] border border-[#2e2e50] rounded-xl p-4">
                    <p className="text-xs font-bold text-[#8888aa] uppercase mb-3">
                      Trades (showing {Math.min(sigData!.trades.length, 50)})
                    </p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-[#555570] text-left">
                            <th className="pb-2 pr-3">Ticker</th>
                            <th className="pb-2 pr-3">Entry</th>
                            <th className="pb-2 pr-3">Exit</th>
                            <th className="pb-2 pr-3 text-right">Net P&L</th>
                            <th className="pb-2">Reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sigData!.trades.slice(0, 50).map((t, i) => (
                            <tr key={i} className="border-t border-[#2e2e50]">
                              <td className="py-1.5 pr-3 font-bold text-white">{t.ticker}</td>
                              <td className="py-1.5 pr-3 text-[#8888aa]">{t.entry_date}</td>
                              <td className="py-1.5 pr-3 text-[#8888aa]">{t.exit_date}</td>
                              <td className={`py-1.5 pr-3 text-right font-bold ${t.net_profit_pct >= 0 ? "text-[#00e676]" : "text-[#ff5252]"}`}>
                                {pct(t.net_profit_pct)}
                              </td>
                              <td className="py-1.5">
                                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                                  t.exit_reason === "take_profit" ? "bg-[#00e676]/20 text-[#00e676]"
                                  : t.exit_reason === "stop_loss" ? "bg-[#ff5252]/20 text-[#ff5252]"
                                  : "bg-[#2e2e50] text-[#8888aa]"
                                }`}>
                                  {t.exit_reason.replace("_", " ")}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

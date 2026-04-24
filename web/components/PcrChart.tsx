"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, Area, AreaChart,
} from "recharts";
import { format, parseISO } from "date-fns";
import type { PcrSnapshot } from "@/lib/types";

interface Props {
  snapshots: PcrSnapshot[];
}

function pcrColor(pcr: number): string {
  if (pcr > 1.0) return "#ef4444";
  if (pcr < 0.5) return "#22c55e";
  return "#9ca3af";
}

export default function PcrChart({ snapshots }: Props) {
  if (!snapshots.length) {
    return (
      <div className="flex h-48 items-center justify-center text-[#8888aa] text-sm">
        No PCR history yet — check back after the next pipeline run.
      </div>
    );
  }

  const data = snapshots.map((s) => ({
    time:  format(parseISO(s.snapshot_at), "HH:mm"),
    pcr:   s.pcr ?? 0,
    puts:  s.put_volume ?? 0,
    calls: s.call_volume ?? 0,
    label: s.pcr_label ?? "",
  }));

  const maxPcr = Math.max(...data.map((d) => d.pcr), 2);

  return (
    <div className="space-y-3">
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="pcrGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#2e2e50" />
          <XAxis dataKey="time" tick={{ fill: "#8888aa", fontSize: 11 }} />
          <YAxis
            domain={[0, Math.ceil(maxPcr * 1.1)]}
            tick={{ fill: "#8888aa", fontSize: 11 }}
            tickCount={5}
          />
          <Tooltip
            contentStyle={{ background: "#1a1a2e", border: "1px solid #2e2e50", borderRadius: 8 }}
            labelStyle={{ color: "#fff" }}
            formatter={(value: number, name: string) => {
              if (name === "pcr") return [value.toFixed(3), "PCR"];
              return [value.toLocaleString(), name];
            }}
          />
          {/* Fear boundary */}
          <ReferenceLine y={1.0} stroke="#ef4444" strokeDasharray="4 4"
            label={{ value: "Fear", fill: "#ef4444", fontSize: 11, position: "insideTopRight" }} />
          {/* Greed boundary */}
          <ReferenceLine y={0.5} stroke="#22c55e" strokeDasharray="4 4"
            label={{ value: "Greed", fill: "#22c55e", fontSize: 11, position: "insideBottomRight" }} />
          <Area
            type="monotone"
            dataKey="pcr"
            stroke="#ef4444"
            strokeWidth={2}
            fill="url(#pcrGrad)"
            dot={{ fill: "#ef4444", r: 3 }}
            activeDot={{ r: 5 }}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Volume bars */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        {data.slice(-1).map((d, i) => (
          <div key={i} className="rounded-lg bg-[#252540] p-3 space-y-1">
            <div className="text-[#8888aa] text-xs">Latest Snapshot</div>
            <div className="flex justify-between">
              <span className="text-red-400">Puts</span>
              <span className="font-mono text-white">{d.puts.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-green-400">Calls</span>
              <span className="font-mono text-white">{d.calls.toLocaleString()}</span>
            </div>
            <div className="flex justify-between font-semibold">
              <span className="text-[#8888aa]">PCR</span>
              <span style={{ color: pcrColor(d.pcr) }}>{d.pcr.toFixed(3)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

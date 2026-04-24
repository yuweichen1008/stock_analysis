"use client";

interface Props {
  putVolume:  number | null;
  callVolume: number | null;
  pcr:        number | null;
}

function fmt(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function PcrBar({ putVolume, callVolume, pcr }: Props) {
  if (putVolume == null && callVolume == null) return null;

  const total = (putVolume ?? 0) + (callVolume ?? 0);
  const putPct  = total > 0 ? ((putVolume ?? 0) / total) * 100 : 50;
  const callPct = 100 - putPct;

  return (
    <div className="space-y-1">
      {/* Bar */}
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-[#2e2e50]">
        <div
          className="h-full bg-red-500 transition-all"
          style={{ width: `${putPct}%` }}
        />
        <div
          className="h-full bg-green-500 transition-all"
          style={{ width: `${callPct}%` }}
        />
      </div>

      {/* Labels */}
      <div className="flex justify-between text-xs text-[#8888aa]">
        <span>
          <span className="text-red-400 font-medium">Puts</span>{" "}
          {fmt(putVolume)}
        </span>
        {pcr != null && (
          <span className="font-semibold text-white">PCR {pcr.toFixed(2)}</span>
        )}
        <span>
          <span className="text-green-400 font-medium">Calls</span>{" "}
          {fmt(callVolume)}
        </span>
      </div>
    </div>
  );
}

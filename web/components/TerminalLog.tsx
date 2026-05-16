"use client";

import { useEffect, useRef, useState } from "react";

export type LogType = "info" | "success" | "error" | "warn" | "fetch";

export interface LogEntry {
  ts: string;
  type: LogType;
  msg: string;
}

const TYPE_COLOR: Record<LogType, string> = {
  fetch:   "#448aff",
  info:    "#8888aa",
  success: "#00e676",
  warn:    "#ffd700",
  error:   "#ff5252",
};

const TYPE_LABEL: Record<LogType, string> = {
  fetch:   "FETCH",
  info:    "INFO ",
  success: "OK   ",
  warn:    "WARN ",
  error:   "ERR  ",
};

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    const ms = String(d.getMilliseconds()).padStart(3, "0");
    return `${hh}:${mm}:${ss}.${ms}`;
  } catch {
    return "--:--:--.---";
  }
}

interface TerminalLogProps {
  logs: LogEntry[];
}

export default function TerminalLog({ logs }: TerminalLogProps) {
  const [open, setOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, open]);

  const last = logs[logs.length - 1];

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-40 bg-[#080810] border-t border-[#2e2e50] font-mono select-none"
      style={{ height: open ? 180 : 28 }}
    >
      {/* Header / collapsed bar */}
      <div className="flex items-center px-3 h-7 gap-2 shrink-0">
        <button
          onClick={() => setOpen(v => !v)}
          className="text-[10px] text-[#555570] hover:text-white transition-colors shrink-0"
          title={open ? "Minimize terminal" : "Expand terminal"}
        >
          {open ? "▼" : "▲"}
        </button>
        <span className="text-[10px] text-[#555570] font-bold uppercase tracking-widest shrink-0">
          Terminal
        </span>
        <span className="text-[10px] text-[#333355] shrink-0">
          · {logs.length}
        </span>
        {last && (
          <span
            className="text-[10px] truncate"
            style={{ color: TYPE_COLOR[last.type] }}
          >
            {last.msg}
          </span>
        )}
        {logs.length > 0 && (
          <button
            onClick={() => {}}
            className="ml-auto text-[9px] text-[#333355] hover:text-[#555570] shrink-0"
            style={{ display: open ? undefined : "none" }}
          >
          </button>
        )}
      </div>

      {/* Log list (visible when open) */}
      {open && (
        <div
          ref={scrollRef}
          className="overflow-y-auto px-3 pb-1"
          style={{ height: 180 - 28 }}
        >
          {logs.length === 0 ? (
            <p className="text-[10px] text-[#333355] pt-2">No log entries yet.</p>
          ) : (
            logs.map((entry, i) => (
              <div key={i} className="flex items-start gap-2 py-px">
                <span className="text-[9px] text-[#333355] shrink-0 pt-px">
                  {fmtTime(entry.ts)}
                </span>
                <span
                  className="text-[9px] font-bold shrink-0 pt-px"
                  style={{ color: TYPE_COLOR[entry.type] }}
                >
                  [{TYPE_LABEL[entry.type]}]
                </span>
                <span className="text-[10px] text-[#ccccdd] break-all leading-tight">
                  {entry.msg}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

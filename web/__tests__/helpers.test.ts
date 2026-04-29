/**
 * Tests for pure helper functions used across the web dashboard.
 * No component rendering, no network calls, no Next.js runtime needed.
 */

import { describe, it, expect } from "vitest";

// ── Inline the helpers here to avoid import issues with Next.js internals ────
// (same logic as in OptionsPage.tsx and WeeklyPage.tsx)

function pcrColor(label: string | null): string {
  if (!label) return "#8888aa";
  if (label.includes("extreme_fear"))  return "#ff5252";
  if (label.includes("fear"))          return "#ff8a65";
  if (label.includes("extreme_greed")) return "#00e676";
  if (label.includes("greed"))         return "#69f0ae";
  return "#8888aa";
}

function fmtSnap(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function pcrLabelColor(label: string | null): string {
  if (!label) return "#8888aa";
  if (label.includes("extreme_fear"))  return "#ff5252";
  if (label.includes("fear"))          return "#ff8a65";
  if (label.includes("extreme_greed")) return "#00e676";
  if (label.includes("greed"))         return "#69f0ae";
  return "#8888aa";
}

// ── pcrColor ──────────────────────────────────────────────────────────────────

describe("pcrColor", () => {
  it("returns neutral grey for null", () => {
    expect(pcrColor(null)).toBe("#8888aa");
  });

  it("returns red for extreme_fear", () => {
    expect(pcrColor("extreme_fear")).toBe("#ff5252");
  });

  it("returns orange for fear", () => {
    expect(pcrColor("fear")).toBe("#ff8a65");
  });

  it("returns green for extreme_greed", () => {
    expect(pcrColor("extreme_greed")).toBe("#00e676");
  });

  it("returns light green for greed", () => {
    expect(pcrColor("greed")).toBe("#69f0ae");
  });

  it("returns neutral grey for unknown label", () => {
    expect(pcrColor("neutral")).toBe("#8888aa");
  });

  it("extreme_fear takes priority over fear substring check", () => {
    // extreme_fear contains 'fear' but should return red, not orange
    expect(pcrColor("extreme_fear")).toBe("#ff5252");
  });

  it("extreme_greed takes priority over greed substring check", () => {
    expect(pcrColor("extreme_greed")).toBe("#00e676");
  });
});

// ── pcrLabelColor (WeeklyPage variant — identical logic) ──────────────────────

describe("pcrLabelColor", () => {
  it("null label returns grey", () => {
    expect(pcrLabelColor(null)).toBe("#8888aa");
  });

  it("fear returns orange", () => {
    expect(pcrLabelColor("fear")).toBe("#ff8a65");
  });

  it("greed returns light green", () => {
    expect(pcrLabelColor("greed")).toBe("#69f0ae");
  });
});

// ── fmtSnap ───────────────────────────────────────────────────────────────────

describe("fmtSnap", () => {
  it("returns dash for null", () => {
    expect(fmtSnap(null)).toBe("—");
  });

  it("returns a non-empty string for a valid ISO timestamp", () => {
    const result = fmtSnap("2026-04-28T14:45:00Z");
    expect(result).toBeTruthy();
    expect(result).not.toBe("—");
  });

  it("contains the day number from the date", () => {
    const result = fmtSnap("2026-04-28T14:45:00Z");
    expect(result).toMatch(/28/);
  });
});

// ── Signal badge label mapping ─────────────────────────────────────────────────

describe("signal type label formatting", () => {
  function formatLabel(type: string): string {
    return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  it("buy_signal formats to 'Buy Signal'", () => {
    expect(formatLabel("buy_signal")).toBe("Buy Signal");
  });

  it("sell_signal formats to 'Sell Signal'", () => {
    expect(formatLabel("sell_signal")).toBe("Sell Signal");
  });

  it("unusual_activity formats to 'Unusual Activity'", () => {
    expect(formatLabel("unusual_activity")).toBe("Unusual Activity");
  });
});

// ── Score badge colour thresholds ─────────────────────────────────────────────

describe("score badge colour", () => {
  function scoreColor(score: number): string {
    return score >= 7 ? "#00e676" : score >= 4 ? "#ffd740" : "#ff8a65";
  }

  it("score >= 7 is green", () => {
    expect(scoreColor(7)).toBe("#00e676");
    expect(scoreColor(10)).toBe("#00e676");
  });

  it("score 4-6.9 is yellow", () => {
    expect(scoreColor(4)).toBe("#ffd740");
    expect(scoreColor(6.9)).toBe("#ffd740");
  });

  it("score < 4 is orange", () => {
    expect(scoreColor(3.9)).toBe("#ff8a65");
    expect(scoreColor(0)).toBe("#ff8a65");
  });
});

// ── IV Rank badge label thresholds ────────────────────────────────────────────

describe("IV rank label", () => {
  function ivLabel(rank: number | null): string {
    if (rank == null) return "—";
    if (rank < 25) return "Low IV";
    if (rank < 50) return "Mid IV";
    return "High IV";
  }

  it("null rank returns dash", () => {
    expect(ivLabel(null)).toBe("—");
  });

  it("rank < 25 is Low IV", () => {
    expect(ivLabel(10)).toBe("Low IV");
    expect(ivLabel(24.9)).toBe("Low IV");
  });

  it("rank 25-49 is Mid IV", () => {
    expect(ivLabel(25)).toBe("Mid IV");
    expect(ivLabel(49.9)).toBe("Mid IV");
  });

  it("rank >= 50 is High IV", () => {
    expect(ivLabel(50)).toBe("High IV");
    expect(ivLabel(99)).toBe("High IV");
  });
});

// ── RSI zone classification ───────────────────────────────────────────────────

describe("RSI zone", () => {
  function rsiZone(rsi: number | null): "oversold" | "overbought" | "neutral" | null {
    if (rsi == null) return null;
    if (rsi < 30) return "oversold";
    if (rsi > 70) return "overbought";
    return "neutral";
  }

  it("RSI < 30 is oversold", () => {
    expect(rsiZone(25)).toBe("oversold");
    expect(rsiZone(29.9)).toBe("oversold");
  });

  it("RSI > 70 is overbought", () => {
    expect(rsiZone(75)).toBe("overbought");
    expect(rsiZone(100)).toBe("overbought");
  });

  it("RSI 30-70 is neutral", () => {
    expect(rsiZone(50)).toBe("neutral");
    expect(rsiZone(30)).toBe("neutral");
    expect(rsiZone(70)).toBe("neutral");
  });

  it("null RSI returns null", () => {
    expect(rsiZone(null)).toBeNull();
  });
});

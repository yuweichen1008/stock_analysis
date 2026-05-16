import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import clsx from "clsx";

export const metadata: Metadata = {
  title: {
    default: "LokiStock — Market Signals & Options Intelligence",
    template: "%s | LokiStock",
  },
  description:
    "Real-time market signals, options screener, backtesting, and CTBC trading — powered by LokiStock Oracle.",
  keywords: ["stock signals", "options screener", "Taiwan stocks", "TAIEX", "backtesting", "PCR"],
  openGraph: {
    siteName: "LokiStock",
    type: "website",
  },
};

const NAV = [
  { href: "/news",      label: "📰 News & PCR" },
  { href: "/tws",       label: "🇹🇼 TWS" },
  { href: "/weekly",    label: "📅 Weekly" },
  { href: "/options",   label: "📈 Options" },
  { href: "/charts",    label: "🕯 Charts" },
  { href: "/backtest",  label: "🔬 Backtest" },
  { href: "/trading",   label: "💹 Trading" },
  { href: "/subscribe", label: "📬 Subscribe" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full flex flex-col bg-[#0d0d14] text-white antialiased">
        {/* Top nav */}
        <header className="shrink-0 border-b border-[#2e2e50] bg-[#0d0d14]/90 backdrop-blur sticky top-0 z-50">
          <div className="mx-auto flex h-14 max-w-screen-2xl items-center px-4 gap-6">
            <Link href="/news" className="flex items-center gap-2 font-bold text-lg shrink-0">
              <span className="text-[#ffd700] text-xl">L</span>
              <span className="text-white">okiStock</span>
            </Link>
            <nav className="flex gap-0.5 overflow-x-auto scrollbar-none">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="rounded-lg px-3 py-1.5 text-sm text-[#8888aa] hover:text-white hover:bg-[#1a1a2e] transition-colors whitespace-nowrap"
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-hidden">{children}</main>

        {/* Footer */}
        <footer className="shrink-0 border-t border-[#2e2e50] bg-[#0d0d14]/90 py-2 px-4">
          <p className="text-center text-[10px] text-[#555570]">
            LokiStock © {new Date().getFullYear()} — Market data for informational purposes only. Not financial advice.
          </p>
        </footer>
      </body>
    </html>
  );
}

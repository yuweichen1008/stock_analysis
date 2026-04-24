import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import clsx from "clsx";

export const metadata: Metadata = {
  title: "Oracle Dashboard",
  description: "Stock news, put/call ratio, and market signals",
};

const NAV = [
  { href: "/news",      label: "📰 News & PCR" },
  { href: "/subscribe", label: "📬 Subscribe" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full flex flex-col bg-[#0d0d14] text-white antialiased">
        {/* Top nav */}
        <header className="shrink-0 border-b border-[#2e2e50] bg-[#0d0d14]/90 backdrop-blur sticky top-0 z-50">
          <div className="mx-auto flex h-14 max-w-screen-2xl items-center px-4 gap-6">
            <Link href="/news" className="flex items-center gap-2 font-bold text-lg">
              🔮 <span className="text-white">Oracle</span>
            </Link>
            <nav className="flex gap-1">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="rounded-lg px-3 py-1.5 text-sm text-[#8888aa] hover:text-white hover:bg-[#1a1a2e] transition-colors"
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-hidden">{children}</main>
      </body>
    </html>
  );
}

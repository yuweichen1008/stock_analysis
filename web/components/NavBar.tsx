"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/",          label: "🏠 Home" },
  { href: "/tws",       label: "💼 Portfolio" },
  { href: "/news",      label: "📰 News" },
  { href: "/weekly",    label: "📅 Weekly" },
  { href: "/options",   label: "📈 Options" },
  { href: "/charts",    label: "🕯 Charts" },
  { href: "/backtest",  label: "🔬 Backtest" },
  { href: "/trading",   label: "💹 Trading" },
  { href: "/subscribe", label: "📬 Subscribe" },
];

export default function NavBar() {
  const path = usePathname();
  return (
    <nav className="flex gap-0.5 overflow-x-auto scrollbar-none">
      {NAV.map(n => {
        const active = n.href === "/"
          ? path === "/"
          : path === n.href || path.startsWith(n.href + "/");
        return (
          <Link
            key={n.href}
            href={n.href}
            className={[
              "rounded-lg px-3 py-1.5 text-sm transition-colors whitespace-nowrap",
              active
                ? "text-white bg-[#1a1a2e] border border-[#2e2e50]"
                : "text-[#8888aa] hover:text-white hover:bg-[#1a1a2e]",
            ].join(" ")}
          >
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}

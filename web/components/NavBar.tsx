"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/",          label: "Home" },
  { href: "/tws",       label: "Portfolio" },
  { href: "/news",      label: "News" },
  { href: "/weekly",    label: "Weekly" },
  { href: "/options",   label: "Options" },
  { href: "/charts",    label: "Charts" },
  { href: "/backtest",  label: "Backtest" },
  { href: "/trading",   label: "Trading" },
  { href: "/subscribe", label: "Subscribe" },
];

export default function NavBar() {
  const path = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  return (
    <nav className="flex items-center gap-0.5 overflow-x-auto scrollbar-none">
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

      {/* Auth section — pushed to right */}
      <div className="ml-auto pl-2 shrink-0">
        {user ? (
          <div className="flex items-center gap-1.5">
            <Link
              href="/profile"
              className={[
                "flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors whitespace-nowrap",
                path === "/profile"
                  ? "text-white bg-[#1a1a2e] border border-[#2e2e50]"
                  : "text-[#8888aa] hover:text-white hover:bg-[#1a1a2e]",
              ].join(" ")}
            >
              <span className="w-5 h-5 rounded-full bg-[#7c5cfc33] flex items-center justify-center text-[10px] font-bold text-[#7c5cfc]">
                {(user.display_name || user.email || "?")[0].toUpperCase()}
              </span>
              <span className="hidden sm:inline max-w-[100px] truncate">{user.display_name}</span>
            </Link>
            <button
              onClick={() => { logout(); router.push("/"); }}
              className="rounded-lg px-2.5 py-1.5 text-xs text-[#6666aa] hover:text-white hover:bg-[#1a1a2e] transition-colors whitespace-nowrap"
            >
              Sign out
            </button>
          </div>
        ) : (
          <Link
            href="/login"
            className="rounded-lg px-3 py-1.5 text-sm font-medium bg-[#7c5cfc] hover:bg-[#8f72ff] text-white transition-colors whitespace-nowrap"
          >
            Sign In
          </Link>
        )}
      </div>
    </nav>
  );
}

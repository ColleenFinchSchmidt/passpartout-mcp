"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { settings } from "@/settings";
import type { Locale } from "@/i18n";
import { t } from "@/i18n";

const navItems = [
  { key: "results" as const, href: "/results" },
  { key: "offers" as const, href: "/offers" },
  { key: "calendar" as const, href: "/calendar" },
  { key: "setup" as const, href: "/setup" },
];

export default function Nav({
  locale,
  onToggleLocale,
}: {
  locale: Locale;
  onToggleLocale: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const labels = t(locale).nav;

  async function handleLogout() {
    await fetch("/api/demo-login", { method: "DELETE" });
    router.push("/login");
    router.refresh();
  }

  return (
    <nav className="sticky top-0 z-50 bg-[var(--color-nav-bg)] border-b border-[var(--color-border)]">
      <div className="max-w-6xl mx-auto px-4 flex items-center justify-between h-14">
        {/* Left: nav links */}
        <div className="flex items-center gap-1 overflow-x-auto">
          {navItems.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.key}
                href={item.href}
                className={`px-3 py-1.5 text-sm font-medium rounded-[var(--radius-button)] whitespace-nowrap transition-colors ${
                  active
                    ? "bg-[var(--color-accent-light)] text-[var(--color-accent)]"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)]"
                }`}
              >
                {labels[item.key]}
              </Link>
            );
          })}
        </div>

        {/* Right: demo badge, locale toggle, hotel name */}
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs font-medium px-2 py-0.5 rounded-[var(--radius-badge)] bg-[var(--color-amber-light)] text-[var(--color-amber)]">
            {t(locale).demo}
          </span>
          <button
            onClick={onToggleLocale}
            className="text-xs font-medium px-2 py-1 rounded-[var(--radius-badge)] border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-text-muted)] transition-colors"
          >
            {locale === "en" ? "IT" : "EN"}
          </button>
          <span className="text-sm font-medium text-[var(--color-text)] hidden sm:block">
            {settings.demoHotelName}
          </span>
          <button
            onClick={handleLogout}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            {labels.logout}
          </button>
        </div>
      </div>
    </nav>
  );
}

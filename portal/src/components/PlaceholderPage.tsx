"use client";

import { useLocale } from "./LocaleProvider";
import { t } from "@/i18n";

export default function PlaceholderPage({
  section,
}: {
  section: "offers" | "calendar" | "results" | "setup";
}) {
  const { locale } = useLocale();
  const labels = t(locale)[section];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{labels.title}</h1>
      {"comingSoon" in labels && (
        <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-[var(--radius-card)] p-6">
          <p className="text-[var(--color-text-muted)]">
            {(labels as { comingSoon: string }).comingSoon}
          </p>
        </div>
      )}
    </div>
  );
}

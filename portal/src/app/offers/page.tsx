"use client";

import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/i18n";

export default function OffersPage() {
  const { locale } = useLocale();
  const labels = t(locale).offers;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{labels.title}</h1>
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-[var(--radius-card)] p-6">
        <p className="text-[var(--color-text-muted)]">{labels.empty}</p>
      </div>
    </div>
  );
}

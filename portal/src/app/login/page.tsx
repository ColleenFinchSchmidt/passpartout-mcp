"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { settings } from "@/settings";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/i18n";

export default function LoginPage() {
  const { locale, toggle } = useLocale();
  const labels = t(locale).login;
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleDemoLogin() {
    setLoading(true);
    const res = await fetch("/api/demo-login", { method: "POST" });
    if (res.ok) {
      router.push("/offers");
      router.refresh();
    }
    setLoading(false);
  }

  return (
    <div className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center space-y-2">
          <div className="mx-auto w-10 h-10 rounded-xl bg-[var(--color-accent)] flex items-center justify-center">
            <span className="text-white font-bold text-lg font-[family-name:var(--font-space-grotesk)]">P</span>
          </div>
          <h1 className="text-xl font-semibold font-[family-name:var(--font-space-grotesk)]">
            {settings.productName}
          </h1>
          <p className="text-sm text-[var(--color-text-muted)]">
            {labels.subtitle}
          </p>
        </div>

        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-base">{labels.title}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-[var(--color-text)]">
                {labels.email}
              </label>
              <Input
                type="email"
                placeholder="you@hotel.com"
                disabled
              />
            </div>
            <Button className="w-full" disabled>
              {labels.send}
            </Button>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-[var(--color-border)]" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-white px-2 text-[var(--color-text-muted)]">or</span>
              </div>
            </div>

            <Button
              variant="secondary"
              className="w-full"
              onClick={handleDemoLogin}
              disabled={loading}
            >
              {labels.demoLogin}
            </Button>
            <p className="text-xs text-center text-[var(--color-text-muted)]">
              {labels.demoHint}
            </p>
          </CardContent>
        </Card>

        <div className="text-center">
          <button
            onClick={toggle}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors cursor-pointer"
          >
            {locale === "en" ? "Italiano" : "English"}
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { createContext, useContext, useState, useCallback } from "react";
import type { Locale } from "@/i18n";
import { settings } from "@/settings";

const LocaleContext = createContext<{
  locale: Locale;
  toggle: () => void;
}>({
  locale: settings.defaultLocale,
  toggle: () => {},
});

export function useLocale() {
  return useContext(LocaleContext);
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>(settings.defaultLocale);
  const toggle = useCallback(
    () => setLocale((l) => (l === "en" ? "it" : "en")),
    [],
  );

  return (
    <LocaleContext.Provider value={{ locale, toggle }}>
      {children}
    </LocaleContext.Provider>
  );
}

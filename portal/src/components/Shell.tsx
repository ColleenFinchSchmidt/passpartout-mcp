"use client";

import Nav from "./Nav";
import { LocaleProvider, useLocale } from "./LocaleProvider";

function ShellInner({ children }: { children: React.ReactNode }) {
  const { locale, toggle } = useLocale();
  return (
    <>
      <Nav locale={locale} onToggleLocale={toggle} />
      <main className="max-w-6xl mx-auto px-4 py-6 flex-1">{children}</main>
    </>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  return (
    <LocaleProvider>
      <ShellInner>{children}</ShellInner>
    </LocaleProvider>
  );
}

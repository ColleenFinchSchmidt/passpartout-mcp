import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import Shell from "@/components/Shell";
import { settings } from "@/settings";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: `${settings.productName} · Hotel Portal`,
  description: settings.tagline,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${spaceGrotesk.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-[var(--color-bg)] text-[var(--color-text)]">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}

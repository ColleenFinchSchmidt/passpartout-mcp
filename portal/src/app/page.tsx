import { redirect } from "next/navigation";

export const instant = false;

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

async function hasPendingOffers(): Promise<boolean> {
  try {
    const headers: Record<string, string> = {};
    if (API_KEY) headers["x-api-key"] = API_KEY;

    const res = await fetch(
      `${ENGINE_URL}/api/hotel/offers-timeline?hotel_id=bristol-stresa`,
      { cache: "no-store", headers, signal: AbortSignal.timeout(8000) },
    );
    if (!res.ok) return false;

    const data = await res.json();
    const periods: Array<{ has_offer?: boolean }> = data.periods ?? [];
    return periods.some((p) => p.has_offer);
  } catch {
    return false;
  }
}

export default async function Home() {
  const pending = await hasPendingOffers();
  redirect(pending ? "/offers" : "/results");
}

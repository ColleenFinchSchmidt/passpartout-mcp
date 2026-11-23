import OffersList from "./OffersList";

export const instant = false;

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

export default async function OffersPage() {
  let suggestions: Array<Record<string, unknown>> = [];
  let engineError = "";

  try {
    const url = `${ENGINE_URL}/api/hotel/suggest?hotel_id=bristol-stresa`;
    const headers: Record<string, string> = {};
    if (API_KEY) headers["x-api-key"] = API_KEY;

    const res = await fetch(url, { cache: "no-store", headers });
    if (res.ok) {
      const data = await res.json();
      suggestions = data.suggestions ?? [];
    } else {
      engineError = `Engine returned ${res.status}`;
    }
  } catch (e) {
    engineError = e instanceof Error ? e.message : "Engine unreachable";
  }

  return (
    <OffersList
      suggestions={suggestions}
      engineError={engineError}
    />
  );
}

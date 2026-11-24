import { NextResponse } from "next/server";

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

export async function GET() {
  try {
    const headers: Record<string, string> = {};
    if (API_KEY) headers["x-api-key"] = API_KEY;

    const signal = AbortSignal.timeout(15000);
    const res = await fetch(
      `${ENGINE_URL}/api/hotel/profile?hotel_id=bristol-stresa`,
      { cache: "no-store", headers, signal }
    );

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return NextResponse.json({
        error: `Engine returned ${res.status}`,
        detail: text.slice(0, 500),
        engine_url: ENGINE_URL,
        has_api_key: !!API_KEY,
      });
    }

    const data = await res.json();
    return NextResponse.json({
      ok: true,
      has_hotel_profile: !!data._hotel_profile,
      has_process_started_at: !!data.process_started_at,
      hotel_name: data._hotel_profile?.name,
      extras_count: data._hotel_profile?.extras?.length ?? 0,
      engine_url: ENGINE_URL,
      has_api_key: !!API_KEY,
    });
  } catch (err) {
    return NextResponse.json({
      error: "Fetch failed",
      message: err instanceof Error ? err.message : String(err),
      engine_url: ENGINE_URL,
      has_api_key: !!API_KEY,
    });
  }
}

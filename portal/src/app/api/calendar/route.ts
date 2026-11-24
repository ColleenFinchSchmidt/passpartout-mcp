import { NextRequest, NextResponse } from "next/server";

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const year = searchParams.get("year") || "";
  const month = searchParams.get("month") || "";

  const params = new URLSearchParams({ hotel_id: "bristol-stresa" });
  if (year) params.set("year", year);
  if (month) params.set("month", month);

  const headers: Record<string, string> = {};
  if (API_KEY) headers["x-api-key"] = API_KEY;

  const res = await fetch(`${ENGINE_URL}/api/hotel/calendar?${params}`, {
    headers,
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = "";
    try { detail = await res.text(); } catch {}
    return NextResponse.json(
      { error: `Engine returned ${res.status}`, detail },
      { status: res.status },
    );
  }
  return NextResponse.json(await res.json());
}

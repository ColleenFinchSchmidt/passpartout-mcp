import { NextResponse } from "next/server";

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

export async function GET() {
  const headers: Record<string, string> = {};
  if (API_KEY) headers["x-api-key"] = API_KEY;

  const res = await fetch(
    `${ENGINE_URL}/api/hotel/results?hotel_id=bristol-stresa`,
    { headers, cache: "no-store" },
  );
  if (!res.ok) {
    return NextResponse.json({ error: `Engine returned ${res.status}` }, { status: res.status });
  }
  return NextResponse.json(await res.json());
}

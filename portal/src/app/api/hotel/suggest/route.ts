import { NextResponse } from "next/server";

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

export async function GET() {
  const url = `${ENGINE_URL}/api/hotel/suggest?hotel_id=bristol-stresa`;
  const headers: Record<string, string> = {};
  if (API_KEY) headers["x-api-key"] = API_KEY;

  const res = await fetch(url, { headers, cache: "no-store" });
  if (!res.ok) {
    return NextResponse.json(
      { error: `Engine returned ${res.status}` },
      { status: res.status }
    );
  }
  const data = await res.json();
  return NextResponse.json(data);
}

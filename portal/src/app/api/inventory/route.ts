import { NextRequest, NextResponse } from "next/server";

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) h["x-api-key"] = API_KEY;
  return h;
}

export async function GET(req: NextRequest) {
  const hotelId = req.nextUrl.searchParams.get("hotel_id") || "";
  const url = `${ENGINE_URL}/api/hotel/inventory?hotel_id=${encodeURIComponent(hotelId)}`;
  const res = await fetch(url, { cache: "no-store", headers: headers() });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const url = `${ENGINE_URL}/api/hotel/inventory`;
  const res = await fetch(url, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

import { NextRequest, NextResponse } from "next/server";

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) h["x-api-key"] = API_KEY;
  return h;
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const { offer_id, extra_to_add } = body;
  if (!offer_id) {
    return NextResponse.json({ error: "offer_id required" }, { status: 400 });
  }
  const url = `${ENGINE_URL}/api/hotel/inventory/${encodeURIComponent(offer_id)}/wave`;
  const res = await fetch(url, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ extra_to_add: extra_to_add ?? null }),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

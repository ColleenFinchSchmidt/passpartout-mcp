import { NextRequest, NextResponse } from "next/server";

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) h["x-api-key"] = API_KEY;
  return h;
}

export async function GET() {
  const res = await fetch(
    `${ENGINE_URL}/api/hotel/rules?hotel_id=bristol-stresa`,
    { headers: headers(), cache: "no-store" },
  );
  if (!res.ok) {
    return NextResponse.json({ error: `Engine returned ${res.status}` }, { status: res.status });
  }
  return NextResponse.json(await res.json());
}

export async function PUT(req: NextRequest) {
  const body = await req.json();
  const res = await fetch(
    `${ENGINE_URL}/api/hotel/rules?hotel_id=bristol-stresa`,
    { method: "PUT", headers: headers(), body: JSON.stringify(body), cache: "no-store" },
  );
  if (!res.ok) {
    return NextResponse.json({ error: `Engine returned ${res.status}` }, { status: res.status });
  }
  return NextResponse.json(await res.json());
}

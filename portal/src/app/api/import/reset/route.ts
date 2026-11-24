import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const HOTEL_ID = "bristol-stresa";
const ENGINE_URL = process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

export async function POST(request: NextRequest) {
  const isLoggedIn = request.cookies.get("passpartout_demo")?.value === "1";
  if (!isLoggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  try {
    // Clear engine Postgres data
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (API_KEY) headers["x-api-key"] = API_KEY;

    const engineRes = await fetch(
      `${ENGINE_URL}/api/import/reset?hotel_id=${HOTEL_ID}`,
      { method: "POST", headers },
    );

    let engineResult = null;
    if (engineRes.ok) {
      engineResult = await engineRes.json();
    } else {
      const errText = await engineRes.text().catch(() => "");
      engineResult = { error: `Engine ${engineRes.status}`, detail: errText.slice(0, 200) };
    }

    // Clear portal import history
    await prisma.importRow.deleteMany({ where: { batch: { hotelId: HOTEL_ID } } });
    await prisma.importBatch.deleteMany({ where: { hotelId: HOTEL_ID } });

    return NextResponse.json({ reset: true, engineResult });
  } catch (err) {
    console.error("[import/reset] error:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Reset failed" }, { status: 500 });
  }
}

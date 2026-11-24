import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const HOTEL_ID = "bristol-stresa";

export async function POST() {
  try {
    const result = await prisma.guest.deleteMany({
      where: { hotelId: HOTEL_ID },
    });

    return NextResponse.json({ deleted: true, count: result.count });
  } catch (err) {
    console.error("[import/delete-guests] error:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Delete failed" }, { status: 500 });
  }
}

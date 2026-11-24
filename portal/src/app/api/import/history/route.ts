import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const HOTEL_ID = "bristol-stresa";

export async function GET() {
  try {
    const batches = await prisma.importBatch.findMany({
      where: { hotelId: HOTEL_ID, undone: false },
      orderBy: { createdAt: "desc" },
      take: 50,
    });

    return NextResponse.json(
      batches.map(b => ({
        id: b.id,
        fileName: b.fileName,
        importedAt: b.createdAt.toISOString(),
        categories: b.categories,
        rowCounts: b.rowCounts,
      }))
    );
  } catch (err) {
    console.error("[import/history] error:", err instanceof Error ? err.message : err);
    return NextResponse.json([]);
  }
}

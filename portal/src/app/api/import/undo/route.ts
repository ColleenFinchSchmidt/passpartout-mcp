import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const { importId } = await request.json();
    if (!importId) {
      return NextResponse.json({ error: "No importId" }, { status: 400 });
    }

    await prisma.$transaction([
      prisma.importRow.deleteMany({ where: { batchId: importId } }),
      prisma.guest.deleteMany({ where: { batchId: importId } }),
      prisma.importBatch.update({
        where: { id: importId },
        data: { undone: true, undoneAt: new Date() },
      }),
    ]);

    return NextResponse.json({ undone: true });
  } catch (err) {
    console.error("[import/undo] error:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Undo failed" }, { status: 500 });
  }
}

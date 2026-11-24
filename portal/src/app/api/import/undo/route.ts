import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const { importId } = await request.json();
    if (!importId) {
      return NextResponse.json({ error: "No importId" }, { status: 400 });
    }

    const batch = await prisma.importBatch.findUnique({
      where: { id: importId },
      include: { guests: { select: { id: true } } },
    });

    if (!batch) {
      return NextResponse.json({ error: "Batch not found" }, { status: 404 });
    }

    await prisma.importRow.deleteMany({ where: { batchId: importId } });

    // Disconnect guests from this batch, then delete orphans
    for (const guest of batch.guests) {
      await prisma.guest.update({
        where: { id: guest.id },
        data: { batches: { disconnect: { id: importId } } },
      });

      const remaining = await prisma.guest.findUnique({
        where: { id: guest.id },
        include: { _count: { select: { batches: true } } },
      });

      if (remaining && remaining._count.batches === 0) {
        await prisma.guest.delete({ where: { id: guest.id } });
      }
    }

    await prisma.importBatch.update({
      where: { id: importId },
      data: { undone: true, undoneAt: new Date() },
    });

    return NextResponse.json({ undone: true });
  } catch (err) {
    console.error("[import/undo] error:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Undo failed" }, { status: 500 });
  }
}

import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const { importId } = await request.json();
    if (!importId) {
      return NextResponse.json({ error: "No importId" }, { status: 400 });
    }

    // TODO: Undo import in Postgres (delete rows by import batch).
    console.log(`[import/undo] Undoing import ${importId}`);

    return NextResponse.json({ undone: true });
  } catch (err) {
    console.error("[import/undo] error:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Undo failed" }, { status: 500 });
  }
}

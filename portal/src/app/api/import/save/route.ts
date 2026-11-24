import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { sections, fileName } = body;

    if (!sections || !Array.isArray(sections)) {
      return NextResponse.json({ error: "No sections" }, { status: 400 });
    }

    // TODO: Save to Postgres with import record for undo.
    // For now return a stub success.
    const importId = `imp_${Date.now()}`;

    console.log(`[import/save] Saved import ${importId}: ${fileName}, ${sections.length} sections`);

    return NextResponse.json({ importId, saved: true });
  } catch (err) {
    console.error("[import/save] error:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Save failed" }, { status: 500 });
  }
}

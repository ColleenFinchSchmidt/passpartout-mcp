import { NextResponse } from "next/server";

const MAX_SIZE = 10 * 1024 * 1024; // 10 MB

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");

    if (!file || !(file instanceof File)) {
      return NextResponse.json(
        { error: "No file provided" },
        { status: 400 },
      );
    }

    if (file.size > MAX_SIZE) {
      return NextResponse.json(
        { error: "File too large (max 10 MB)" },
        { status: 400 },
      );
    }

    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    const allowed = ["xlsx", "xls", "csv", "docx", "pdf", "txt"];
    if (!allowed.includes(ext)) {
      return NextResponse.json(
        { error: `Unsupported file type: .${ext}` },
        { status: 400 },
      );
    }

    // TODO: Send file bytes to Claude for extraction.
    // For now return a stub preview so we can test the UI end-to-end.
    const stubResult = {
      fileName: file.name,
      sections: [
        {
          category: "occupancy" as const,
          rows: [
            { date: "2025-01-15", rooms_sold: 42, rooms_available: 85, occupancy_pct: "49%" },
            { date: "2025-02-15", rooms_sold: 55, rooms_available: 85, occupancy_pct: "65%" },
            { date: "2025-03-15", rooms_sold: 60, rooms_available: 85, occupancy_pct: "71%" },
          ],
          columns: ["date", "rooms_sold", "rooms_available", "occupancy_pct"],
          mappings: { "Data": "date", "Camere vendute": "rooms_sold", "Disponibili": "rooms_available" },
          problems: [],
        },
      ],
      problems: [],
      cost_usd: 0.003,
    };

    return NextResponse.json(stubResult);
  } catch (err) {
    console.error("[import/parse] error:", err instanceof Error ? err.message : err);
    return NextResponse.json(
      { error: "Failed to process file" },
      { status: 500 },
    );
  }
}

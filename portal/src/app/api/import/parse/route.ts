import { NextRequest, NextResponse } from "next/server";

const ENGINE_URL =
  process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";
const MAX_SIZE = 10 * 1024 * 1024; // 10 MB

export async function POST(request: NextRequest) {
  const isLoggedIn = request.cookies.get("passpartout_demo")?.value === "1";
  if (!isLoggedIn) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
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

    // Forward the file to the engine's parse endpoint
    const engineForm = new FormData();
    engineForm.append("file", file);

    const headers: Record<string, string> = {};
    if (API_KEY) headers["x-api-key"] = API_KEY;

    const url = new URL(request.url);
    const modelParam = url.searchParams.get("model");
    const parseUrl = new URL(`${ENGINE_URL}/api/import/parse-file`);
    if (modelParam) parseUrl.searchParams.set("model", modelParam);

    const res = await fetch(parseUrl.toString(), {
      method: "POST",
      headers,
      body: engineForm,
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: `Engine returned ${res.status}` }));
      return NextResponse.json(
        { error: data.detail || data.error || `Parse failed (${res.status})` },
        { status: res.status },
      );
    }

    return NextResponse.json(await res.json());
  } catch (err) {
    console.error("[import/parse] error:", err instanceof Error ? err.message : err);
    return NextResponse.json(
      { error: "Failed to process file" },
      { status: 500 },
    );
  }
}

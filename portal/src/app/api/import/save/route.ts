import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import type { Prisma } from "@/generated/prisma/client";

const HOTEL_ID = "bristol-stresa";
const ENGINE_URL = process.env.ENGINE_URL || "https://web-production-eb412a2e.up.railway.app";
const API_KEY = process.env.HOTEL_API_KEY || "";

type Section = {
  category: string;
  rows: Record<string, unknown>[];
  columns: string[];
  mappings: Record<string, string>;
  problems: { message: string; count?: number }[];
};

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { sections, fileName, modelUsed } = body as { sections: Section[]; fileName: string; modelUsed?: string };

    if (!sections || !Array.isArray(sections) || sections.length === 0) {
      return NextResponse.json({ error: "No sections to save" }, { status: 400 });
    }

    const rowCounts: Record<string, number> = {};
    const stats = { guestsStored: 0, guestsSkippedConsent: 0, guestsDeduplicated: 0 };

    for (const s of sections) {
      rowCounts[s.category] = s.rows.length;
    }

    const batch = await prisma.importBatch.create({
      data: {
        hotelId: HOTEL_ID,
        fileName,
        categories: sections.map(s => s.category),
        rowCounts,
        modelUsed: modelUsed || sections.map(s => (s as Record<string, unknown>).model_used || "unknown").join(", "),
        rows: {
          create: sections.flatMap(s =>
            s.rows.map(row => ({
              category: s.category,
              data: row as Prisma.InputJsonValue,
            }))
          ),
        },
      },
    });

    for (const s of sections) {
      if (s.category !== "guests") continue;
      for (const row of s.rows) {
        const email = (row.email as string)?.trim() || null;
        const phone = (row.phone as string)?.trim() || null;
        if (!email && !phone) continue;

        const hasConsent = row.marketing_consent === true || row.marketing_consent === "true" || row.marketing_consent === "yes" || row.marketing_consent === "sì" || row.marketing_consent === "si";
        if (!hasConsent) {
          stats.guestsSkippedConsent++;
          continue;
        }

        const guestData = {
          hotelId: HOTEL_ID,
          firstName: (row.first_name as string) || null,
          lastName: (row.last_name as string) || null,
          email: email,
          phone: phone,
          city: (row.city as string) || null,
          stays: typeof row.stays === "number" ? row.stays : 0,
          lastStayDate: (row.last_stay_date as string) || null,
          marketingConsent: true,
          consentDate: (row.consent_date as string) || null,
          consentSource: `import:${fileName}`,
        };

        let existing = null;

        if (email) {
          existing = await prisma.guest.findUnique({
            where: { hotelId_email: { hotelId: HOTEL_ID, email } },
          });
        }
        if (!existing && phone) {
          existing = await prisma.guest.findFirst({
            where: { hotelId: HOTEL_ID, phone },
          });
        }

        if (existing) {
          stats.guestsDeduplicated++;
          await prisma.guest.update({
            where: { id: existing.id },
            data: {
              ...guestData,
              batches: { connect: { id: batch.id } },
            },
          });
        } else {
          await prisma.guest.create({
            data: {
              ...guestData,
              batches: { connect: { id: batch.id } },
            },
          });
        }
        stats.guestsStored++;
      }
    }

    // Apply to engine (best-effort — don't fail the import if engine is down)
    let engineApplied = null;
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (API_KEY) headers["x-api-key"] = API_KEY;
      const engineRes = await fetch(`${ENGINE_URL}/api/import/apply`, {
        method: "POST",
        headers,
        body: JSON.stringify({ hotel_id: HOTEL_ID, sections }),
      });
      if (engineRes.ok) {
        engineApplied = await engineRes.json();
      } else {
        const errText = await engineRes.text().catch(() => "");
        console.error(`[import/save] engine apply failed: ${engineRes.status} ${errText}`);
        engineApplied = { error: `Engine ${engineRes.status}`, detail: errText.slice(0, 200) };
      }
    } catch (e) {
      console.error("[import/save] engine apply error:", e instanceof Error ? e.message : e);
      engineApplied = { error: "Engine unreachable", detail: e instanceof Error ? e.message : String(e) };
    }

    return NextResponse.json({ importId: batch.id, saved: true, stats, engineApplied });
  } catch (err) {
    console.error("[import/save] error:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Save failed" }, { status: 500 });
  }
}

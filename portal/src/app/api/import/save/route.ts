import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import type { Prisma } from "@/generated/prisma/client";

const HOTEL_ID = "bristol-stresa";

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
    const { sections, fileName } = body as { sections: Section[]; fileName: string };

    if (!sections || !Array.isArray(sections) || sections.length === 0) {
      return NextResponse.json({ error: "No sections to save" }, { status: 400 });
    }

    const rowCounts: Record<string, number> = {};
    for (const s of sections) {
      rowCounts[s.category] = s.rows.length;
    }

    const batch = await prisma.importBatch.create({
      data: {
        hotelId: HOTEL_ID,
        fileName,
        categories: sections.map(s => s.category),
        rowCounts,
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

    // Upsert guests from "guests" sections
    for (const s of sections) {
      if (s.category !== "guests") continue;
      for (const row of s.rows) {
        const email = row.email as string | null;
        const phone = row.phone as string | null;
        if (!email && !phone) continue;

        const guestData = {
          hotelId: HOTEL_ID,
          batchId: batch.id,
          firstName: (row.first_name as string) || null,
          lastName: (row.last_name as string) || null,
          email: email || null,
          phone: phone || null,
          city: (row.city as string) || null,
          stays: typeof row.stays === "number" ? row.stays : 0,
          lastStayDate: (row.last_stay_date as string) || null,
          marketingConsent: row.marketing_consent === true,
          consentDate: (row.consent_date as string) || null,
          consentSource: `import:${fileName}`,
        };

        if (email) {
          await prisma.guest.upsert({
            where: { hotelId_email: { hotelId: HOTEL_ID, email } },
            create: guestData,
            update: {
              ...guestData,
              stays: { increment: 0 },
            },
          });
        } else {
          await prisma.guest.create({ data: guestData });
        }
      }
    }

    return NextResponse.json({ importId: batch.id, saved: true });
  } catch (err) {
    console.error("[import/save] error:", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Save failed" }, { status: 500 });
  }
}

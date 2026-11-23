import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const {
    action,
    hotelId,
    guestCity,
    checkIn,
    nights,
    roomsToOffer,
    publicPriceEur,
    privatePriceEur,
    discountPct,
    reasons,
    editedFields,
  } = body;

  if (!["approved", "edited", "skipped"].includes(action)) {
    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  }

  if (action === "edited") {
    const hotel = await prisma.hotel.findUnique({ where: { id: hotelId } });
    if (!hotel) {
      return NextResponse.json({ error: "Hotel not found" }, { status: 404 });
    }

    const editedPrice = editedFields?.privatePriceEur ?? privatePriceEur;
    const editedDiscount =
      ((hotel.publicRateEur - editedPrice) / hotel.publicRateEur) * 100;

    if (editedDiscount > hotel.maxDiscountPct) {
      return NextResponse.json(
        {
          error: `Discount ${editedDiscount.toFixed(1)}% exceeds max ${hotel.maxDiscountPct}%`,
        },
        { status: 422 }
      );
    }
    if (editedPrice < hotel.lowestPriceEur) {
      return NextResponse.json(
        {
          error: `Price €${editedPrice} is below minimum €${hotel.lowestPriceEur}`,
        },
        { status: 422 }
      );
    }
  }

  const record = await prisma.offerAction.create({
    data: {
      hotelId,
      action,
      guestCity,
      checkIn,
      nights,
      roomsToOffer,
      publicPriceEur,
      privatePriceEur: editedFields?.privatePriceEur ?? privatePriceEur,
      discountPct: editedFields?.discountPct ?? discountPct,
      reasons,
      editedFields: action === "edited" ? editedFields : undefined,
    },
  });

  return NextResponse.json({ ok: true, id: record.id });
}

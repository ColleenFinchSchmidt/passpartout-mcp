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
    targetSegment,
    segmentScore,
    packageType,
    inclusions,
    extrasValue,
    extrasCost,
  } = body;

  if (!["approved", "edited", "skipped"].includes(action)) {
    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  }

  const finalPrice = editedFields?.privatePriceEur ?? privatePriceEur;

  if (action === "approved" || action === "edited") {
    const hotel = await prisma.hotel.findUnique({ where: { id: hotelId } });
    if (!hotel) {
      return NextResponse.json({ error: "Hotel not found" }, { status: 404 });
    }

    if (finalPrice < hotel.lowestPriceEur) {
      return NextResponse.json(
        { error: `Price €${finalPrice} is below minimum €${hotel.lowestPriceEur}` },
        { status: 422 },
      );
    }

    const discountPerNight = hotel.publicRateEur - finalPrice;
    const extrasPerNight = extrasCost ?? 0;
    const totalGiveaway = discountPerNight + extrasPerNight;
    const maxGiveaway = hotel.publicRateEur * (hotel.maxDiscountPct / 100);

    if (totalGiveaway > maxGiveaway) {
      return NextResponse.json(
        {
          error: `Total give-away €${totalGiveaway}/night (€${discountPerNight} discount + €${extrasPerNight} extras) exceeds max €${maxGiveaway}/night`,
        },
        { status: 422 },
      );
    }
  }

  const isHoldback = Math.random() < 0.1;

  const record = await prisma.offerAction.create({
    data: {
      hotelId,
      action,
      guestCity,
      checkIn,
      nights,
      roomsToOffer,
      publicPriceEur,
      privatePriceEur: finalPrice,
      discountPct: editedFields?.discountPct ?? discountPct,
      reasons,
      editedFields: action === "edited" ? editedFields : undefined,
      targetSegment: targetSegment ?? null,
      segmentScore: segmentScore ?? null,
      packageType: packageType ?? null,
      inclusions: inclusions ?? [],
      extrasValue: extrasValue ?? null,
      extrasCost: extrasCost ?? null,
      holdback: isHoldback,
    },
  });

  return NextResponse.json({ ok: true, id: record.id });
}

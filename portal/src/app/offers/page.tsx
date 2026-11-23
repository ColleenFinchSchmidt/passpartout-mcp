import { prisma } from "@/lib/db";
import OffersList from "./OffersList";

export default async function OffersPage() {
  const offers = await prisma.offer.findMany({
    orderBy: { checkIn: "asc" },
    include: { hotel: true },
  });

  const plain = offers.map((o) => ({
    id: o.id,
    hotelName: o.hotel.name,
    status: o.status,
    roomType: o.roomType,
    checkIn: o.checkIn.toISOString(),
    checkOut: o.checkOut.toISOString(),
    nights: o.nights,
    roomsAvailable: o.roomsAvailable,
    publicPriceEur: o.publicPriceEur,
    privatePriceEur: o.privatePriceEur,
    discountPct: o.discountPct,
    triggerType: o.triggerType,
    triggerLabel: o.triggerLabel,
    triggerDetail: o.triggerDetail,
    targetGuests: o.targetGuests,
  }));

  return <OffersList offers={plain} />;
}
